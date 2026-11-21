#include "broker_core.h"

#include <algorithm>

#include "../tip/tip_json.h"

namespace broker {

using tip_json::Value;

const char* StopName(Stop stop) {
    switch (stop) {
        case Stop::None: return "none";
        case Stop::Exited: return "exited";
        case Stop::Hang: return "hang";
    }
    return "?";
}

namespace {

bool ParseObject(const std::string& line, Value& value, bool allow_unpaired_values = false) {
    return tip_json::Parser(line, allow_unpaired_values).Parse(value) && value.kind == Value::Object;
}

// {"sid":N, ...the rest of the TIP's object...}
std::string WithSid(ClientId sid, const std::string& object) {
    size_t open = object.find('{');
    size_t body = object.find_first_not_of(" \t\r\n", open + 1);
    std::string head = "{\"sid\":" + std::to_string(sid);
    if (body == std::string::npos || object[body] == '}') return head + "}";
    return head + "," + object.substr(open + 1);
}

std::string SeqState(long long seq, const char* state) {
    return "{\"seq\":" + std::to_string(seq) + ",\"state\":\"" + state + "\"}";
}

// For a TIP without "passes": in the shape of an engine reply, so that it lets the key through.
std::string SeqPass(long long seq, bool direct) {
    return "{\"seq\":" + std::to_string(seq) + ",\"pass_through\":true,\"direct\":" +
           (direct ? "true" : "false") + "}";
}

bool Flag(const Value& msg, const char* key, bool& out) {
    const Value& v = msg.Get(key);
    if (v.kind != Value::Boolean) return false;
    out = v.boolean;
    return true;
}

}  // namespace

const char* Broker::ClientState() const {
    switch (state_) {
        case EngineState::Ready: return "ready";
        case EngineState::Failed: return "down";
        case EngineState::Starting: break;
    }
    return "starting";
}

void Broker::Start() { StartEngine(); }

void Broker::SetState(EngineState state) {
    const char* before = ClientState();
    state_ = state;
    const char* after = ClientState();
    if (std::string(before) != after)
        Broadcast(std::string("{\"event\":\"state\",\"state\":\"") + after + "\"}");
}

void Broker::Broadcast(const std::string& line) {
    for (auto& [id, client] : clients_)
        if (client.hello) platform_.WriteClient(id, line);
}

void Broker::StartEngine() {
    killing_ = false;
    kill_reason_ = Stop::None;
    warnings_.clear();  // a new engine tells its own
    for (auto& [id, client] : clients_) client.session = false;
    SetState(EngineState::Starting);
    Log("starting the engine (" + std::to_string(exits_.size()) +
        " exit(s) in the last 10 minutes)");
    std::string error;
    if (!platform_.StartEngine(error)) {
        Log("the engine could not be started: " + error);
        EngineGone(-1);
    }
}

void Broker::OnClientConnected(ClientId id) { clients_[id] = Client(); }

void Broker::OnClientClosed(ClientId id) {
    auto it = clients_.find(id);
    if (it == clients_.end()) return;
    if (it->second.session && state_ == EngineState::Ready)
        platform_.WriteEngine("{\"op\":\"close\",\"sid\":" + std::to_string(id) + "}");
    clients_.erase(it);
}

void Broker::OnClientLine(ClientId id, const std::string& line) {
    auto it = clients_.find(id);
    if (it == clients_.end()) return;
    Client& client = it->second;
    Value msg;
    // Route the original bytes so the engine can ignore malformed optional fields.
    if (!ParseObject(line, msg, /*allow_unpaired_values=*/true)) {
        Log("unreadable message from a TIP; ignored");
        return;
    }
    const std::string op = msg.Get("op").text;
    long long seq = 0;
    bool has_seq = msg.Get("seq").Int(seq);
    if (op == "hello") {
        if (client.hello) return;
        client.hello = true;
        Flag(msg, "passes", client.passes);
        std::string reply = std::string("{\"proto\":1,\"state\":\"") + ClientState() +
                            "\",\"warnings\":[";
        for (size_t i = 0; i < warnings_.size(); ++i)
            reply += (i ? "," : "") + tip_json::Quote(warnings_[i]);
        reply += "]";
        if (!keymap_.empty()) reply += ",\"keymap\":" + keymap_;
        platform_.WriteClient(id, reply + "}");
        if (state_ == EngineState::Ready) {
            platform_.WriteEngine("{\"op\":\"open\",\"sid\":" + std::to_string(id) + "}");
            client.session = true;
        }
        return;
    }
    if (op == "retry") {
        Retry();
        return;
    }
    if (op == "open_admin") {
        Log("opening the management window");
        platform_.OpenAdmin(msg.Get("tab").text == "words");
        return;
    }
    if (op == "quit") {
        Log("asked to quit (installer)");
        platform_.Quit();
        return;
    }
    if (!client.hello || !has_seq) {
        Log("a request without hello or seq; ignored");
        return;
    }
    if (op == "set_direct") Flag(msg, "direct", client.direct);
    if (state_ != EngineState::Ready) {
        // DESIGN「使えない間の打鍵」: nothing is held; the TIP lets keys through until the engine is ready.
        platform_.WriteClient(id, client.passes ? SeqState(seq, ClientState())
                                                : SeqPass(seq, client.direct));
        return;
    }
    in_flight_.push_back({id, seq, platform_.Now()});
    platform_.WriteEngine(WithSid(id, line));
}

void Broker::OnEngineLine(const std::string& line) {
    Value msg;
    if (!ParseObject(line, msg)) {
        Log("unreadable line from the engine; ignored");
        return;
    }
    if (msg.Get("ready").kind == Value::Boolean && msg.Get("ready").boolean) {
        if (state_ != EngineState::Starting) return;
        Log("engine ready");
        for (const Value& w : msg.Get("warnings").array) Warn(w.text);
        if (msg.Get("keymap").kind == Value::Object)
            UpdateKeymap(tip_json::Stringify(msg.Get("keymap")));
        state_ = EngineState::Ready;
        for (auto& [id, client] : clients_) {
            if (!client.hello) continue;
            platform_.WriteEngine("{\"op\":\"open\",\"sid\":" + std::to_string(id) + "}");
            client.session = true;
        }
        Broadcast("{\"event\":\"state\",\"state\":\"ready\"}");
        return;
    }
    if (msg.Get("event").text == "warning") {
        Warn(msg.Get("warning").text);
        return;
    }
    if (msg.Get("event").text == "keymap") {
        if (msg.Get("keymap").kind == Value::Object)
            UpdateKeymap(tip_json::Stringify(msg.Get("keymap")));
        return;
    }
    long long sid = 0, seq = 0;
    if (!msg.Get("sid").Int(sid) || !msg.Get("seq").Int(seq)) {
        Log("a line from the engine without sid/seq; ignored");
        return;
    }
    // The engine answers in the order it was asked (one request at a time).
    auto it = std::find_if(in_flight_.begin(), in_flight_.end(), [&](const InFlight& f) {
        return f.client == (ClientId)sid && f.seq == seq;
    });
    if (it != in_flight_.begin()) Log("a reply the broker was not waiting for first (sid " +
                                      std::to_string(sid) + ")");
    if (it != in_flight_.end()) in_flight_.erase(it);
    auto client = clients_.find((ClientId)sid);
    if (client == clients_.end()) return;
    Flag(msg, "direct", client->second.direct);
    platform_.WriteClient((ClientId)sid, line);
}

void Broker::UpdateKeymap(const std::string& json) {
    if (keymap_ == json) return;
    keymap_ = json;
    Broadcast("{\"event\":\"keymap\",\"keymap\":" + keymap_ + "}");
}

void Broker::OnEngineStderrLine(const std::string& line) {
    if (line.compare(0, 6, "fatal ") == 0) last_fatal_ = line;
}

// A warning (lm) is logged and listed for the management window; the
// user is not notified (conversion goes on).
void Broker::Warn(const std::string& code) {
    if (code.empty() || std::find(warnings_.begin(), warnings_.end(), code) != warnings_.end())
        return;
    warnings_.push_back(code);
    Log("warning: " + code);
}

void Broker::Kill(Stop reason) {
    if (killing_) return;
    killing_ = true;
    kill_reason_ = reason;
    platform_.KillEngine();
}

void Broker::OnEngineExit(int code) { EngineGone(code); }

// DESIGN「見張り」: an engine that ends is started again at once, unless it is the
// ENGINE_MAX_EXITS-th exit within ENGINE_EXIT_WINDOW_MS: then it stays down
// and the user is told once. "もう一度試す" (Retry) starts it again.
void Broker::EngineGone(int code) {
    bool was_ready = state_ == EngineState::Ready;
    Log("engine exited with code " + std::to_string(code) + (was_ready ? "" : " before ready") +
        (last_fatal_.empty() ? "" : " (" + last_fatal_ + ")"));
    bool restart = restarting_ || (was_ready && code == ENGINE_RESTART_CODE);
    restarting_ = false;
    Stop reason = killing_ && kill_reason_ != Stop::None ? kill_reason_ : Stop::Exited;
    if (!restart) {
        int64_t now = platform_.Now();
        exits_.push_back(now);
        while (now - exits_.front() >= ENGINE_EXIT_WINDOW_MS) exits_.pop_front();
        restart = (int)exits_.size() < ENGINE_MAX_EXITS;
    }
    // The key being processed is lost with the engine; so is every composition.
    const char* next = restart ? "starting" : "down";
    for (const InFlight& f : in_flight_)
        if (clients_.count(f.client)) platform_.WriteClient(f.client, SeqState(f.seq, next));
    in_flight_.clear();
    if (was_ready) Broadcast("{\"event\":\"reset\"}");
    for (auto& [id, client] : clients_) client.session = false;
    if (restart) {
        StartEngine();
        return;
    }
    Log(std::string("engine given up: ") + StopName(reason));
    SetState(EngineState::Failed);
    platform_.NotifyStopped(reason);  // DESIGN「通知」: once; nothing starts by itself after this
}

void Broker::Retry() {
    Log("retry requested");
    exits_.clear();
    last_fatal_.clear();
    if (state_ == EngineState::Failed) {
        platform_.ClearStopped();
        StartEngine();
    } else {
        restarting_ = true;  // e.g. new settings: a fresh engine reads them
        Kill(Stop::None);
    }
}

void Broker::OnTimer() {
    int64_t now = platform_.Now();
    if (state_ == EngineState::Ready && !killing_ && !in_flight_.empty() &&
        now - in_flight_.front().sent >= ENGINE_HANG_MS) {
        Log("no reply from the engine for " + std::to_string(ENGINE_HANG_MS) + " ms; ending it");
        Kill(Stop::Hang);
    }
}

int64_t Broker::NextDeadline() const {
    if (killing_) return NEVER;
    if (state_ == EngineState::Ready && !in_flight_.empty())
        return in_flight_.front().sent + ENGINE_HANG_MS;
    return NEVER;
}

}  // namespace broker

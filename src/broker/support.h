// Pieces beside the Broker: bounded logs, engine.json, and the self-test.
#pragma once

#include <cstdint>
#include <filesystem>
#include <string>
#include <string_view>
#include <vector>

#include "broker_core.h"

namespace broker {

namespace fs = std::filesystem;

constexpr uintmax_t LOG_MAX_BYTES = 1024 * 1024;  // 1 MiB per generation

// What a platform event loop drives: the Broker, or the SelfTest.
class Handler {
public:
    virtual ~Handler() = default;
    virtual void OnClientConnected(ClientId, bool) {}
    virtual void OnClientLine(ClientId, const std::string&) {}
    virtual void OnClientClosed(ClientId) {}
    virtual void OnEngineLine(const std::string& line) = 0;
    virtual void OnEngineStderrLine(const std::string& line) = 0;
    virtual void OnEngineExit(int code) = 0;
    virtual void OnTimer() = 0;
    virtual int64_t NextDeadline() const = 0;
};

class BrokerHandler : public Handler {
public:
    explicit BrokerHandler(Broker& broker) : broker_(broker) {}
    void OnClientConnected(ClientId c, bool app_container) override {
        broker_.OnClientConnected(c, app_container);
    }
    void OnClientLine(ClientId c, const std::string& l) override { broker_.OnClientLine(c, l); }
    void OnClientClosed(ClientId c) override { broker_.OnClientClosed(c); }
    void OnEngineLine(const std::string& l) override { broker_.OnEngineLine(l); }
    void OnEngineStderrLine(const std::string& l) override { broker_.OnEngineStderrLine(l); }
    void OnEngineExit(int code) override { broker_.OnEngineExit(code); }
    void OnTimer() override { broker_.OnTimer(); }
    int64_t NextDeadline() const override { return broker_.NextDeadline(); }

private:
    Broker& broker_;
};

// Keep two generations of up to LOG_MAX_BYTES each. Rotate before a new line
// would overflow the current one. The engine also rotates when it starts.
class BoundedLog {
public:
    BoundedLog(fs::path path, fs::path prev) : path_(path), prev_(prev) {}
    void Write(std::string_view line);  // one line, '\n' added
    bool Rotate();

private:
    fs::path path_, prev_;
};

std::string Timestamp();  // local time, ISO 8601 with milliseconds

// logs/notices.log: one JSON line per stop the user was told about, with its
// time ({"time":..,"stopped":"hang"}). The management window's status tab reads
// the last stop from here (DESIGN「通知」).
void RecordStop(const fs::path& logs, Stop reason);

// engine.json (DESIGN「置き場所」): written by the installer next to the version.
//  {"python":"<abs python.exe>", "pythonw":"<abs pythonw.exe>",
//   "app":"<abs app dir: the engine's working directory>",
//   "args":["-c","<bootstrap>","yuragi.engine", ...],
//   "admin_args":["-c","<bootstrap>","yuragi.ime.admin_ui"]}
struct EngineConfig {
    std::string python, pythonw, app;  // UTF-8
    std::vector<std::string> args, admin_args;
};
bool ReadEngineConfig(const fs::path& path, EngineConfig& config, std::string& error);

// The installer runs --selftest before switching versions. It starts the engine,
// runs one conversion, and shuts the engine down.
enum SelfTestResult {
    SELFTEST_OK = 0,
    SELFTEST_NOT_READY = 1,  // exited, or not ready in time
    SELFTEST_NOT_CONVERTED = 2,
    SELFTEST_NO_REPLY = 4,
    SELFTEST_CANNOT_START = 5,
};

class SelfTestPlatform : public Platform {
public:
    virtual void CloseEngineInput() = 0;
    virtual void Finish(int code) = 0;
};

class SelfTest : public Handler {
public:
    explicit SelfTest(SelfTestPlatform& platform) : platform_(platform) {}
    void Start();
    void OnEngineLine(const std::string& line) override;
    void OnEngineStderrLine(const std::string& line) override;
    void OnEngineExit(int code) override;
    void OnTimer() override;
    int64_t NextDeadline() const override;

private:
    void Send(const std::string& op, int vk, int t);
    void Done(int code, const std::string& why);
    SelfTestPlatform& platform_;
    enum { Starting, Converting, Ending, Finished } phase_ = Starting;
    int64_t deadline_ = 0, poll_at_ = NEVER;
    int poll_key_time_ = 0;
    int sent_ = 0, answered_ = 0;
    bool converted_ = false;
    int result_ = SELFTEST_OK;
    std::string last_fatal_;
};

}  // namespace broker

// The pieces beside the Broker (support.h): the bounded logs, notices.log, and engine.json.
#include "../support.h"

#include <cassert>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <string>

#include "../../tip/tip_json.h"

using namespace broker;

namespace {

std::string Read(const fs::path& path) {
    std::ifstream in(path, std::ios::binary);
    return std::string(std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>());
}

void Write(const fs::path& path, const std::string& text) {
    std::ofstream(path, std::ios::binary) << text;
}

void RotatingLogKeepsTwoGenerations(const fs::path& dir) {
    BoundedLog log(dir / "broker.log", dir / "broker.prev.log");
    const std::string full(LOG_MAX_BYTES - 1, 'x');
    log.Write(full);
    assert(fs::file_size(dir / "broker.log") == LOG_MAX_BYTES);
    assert(!fs::exists(dir / "broker.prev.log"));
    log.Write("last");
    assert(Read(dir / "broker.prev.log") == full + '\n');
    assert(Read(dir / "broker.log") == "last\n");
    log.Write(std::string(LOG_MAX_BYTES, 'x'));
    assert(Read(dir / "broker.log") == "last\n[log line exceeded the size limit; dropped]\n");
}

void EngineLogStartsAfreshWithEachEngine(const fs::path& dir) {
    Write(dir / "engine.log", "the last run\n");
    BoundedLog log(dir / "engine.log", dir / "engine.prev.log");
    assert(log.Rotate());
    assert(Read(dir / "engine.prev.log") == "the last run\n");
    log.Write("this run");
    assert(Read(dir / "engine.log") == "this run\n");
}

// The management window reads the last stop from logs/notices.log (broker_client.last_stop).
void StopsAreRecordedForTheManagementWindow(const fs::path& dir) {
    RecordStop(dir, Stop::Exited);
    RecordStop(dir, Stop::Hang);
    std::string text = Read(dir / "notices.log");
    text.pop_back();
    tip_json::Value last;
    assert(tip_json::Parser(text.substr(text.rfind('\n') + 1)).Parse(last));
    assert(last.Get("stopped").text == "hang" && !last.Get("time").text.empty());
}

// DESIGN「置き場所」: engine.json as PowerShell writes it (indented, maybe with a BOM).
void EngineConfigIsRead(const fs::path& dir) {
    Write(dir / "engine.json", "\xEF\xBB\xBF{\r\n"
          "    \"python\":  \"C:\\\\Users\\\\\xE5\xB1\xB1\xE7\x94\xB0\\\\py\\\\python.exe\",\r\n"
          "    \"pythonw\":  \"C:\\\\py\\\\pythonw.exe\",\r\n"
          "    \"app\":  \"C:\\\\app\",\r\n"
          "    \"args\":  [\"-c\", \"boot\", \"yuragi.engine\"],\r\n"
          "    \"admin_args\":  [\"-c\", \"boot\", \"yuragi.ime.admin_ui\"]\r\n}\r\n");
    EngineConfig config;
    std::string error;
    assert(ReadEngineConfig(dir / "engine.json", config, error));
    assert(config.python == "C:\\Users\\\xE5\xB1\xB1\xE7\x94\xB0\\py\\python.exe");
    assert(config.pythonw == "C:\\py\\pythonw.exe" && config.app == "C:\\app");
    assert((config.args == std::vector<std::string>{"-c", "boot", "yuragi.engine"}));
    assert(config.admin_args.size() == 3 && config.admin_args[2] == "yuragi.ime.admin_ui");

    // Not installed for this user, or cut short: the broker runs without an engine.
    assert(!ReadEngineConfig(dir / "none.json", config, error));
    Write(dir / "engine.json", R"({"python":"C:\\py\\python.exe","app":"C:\\app"})");
    assert(!ReadEngineConfig(dir / "engine.json", config, error) && !error.empty());
}

}  // namespace

int main() {
    const fs::path dir = fs::temp_directory_path() / "yuragi_broker_support_test";
    fs::remove_all(dir);
    fs::create_directories(dir);
    RotatingLogKeepsTwoGenerations(dir);
    EngineLogStartsAfreshWithEachEngine(dir);
    StopsAreRecordedForTheManagementWindow(dir);
    EngineConfigIsRead(dir);
    fs::remove_all(dir);
    std::puts("support_test: all passed");
    return 0;
}

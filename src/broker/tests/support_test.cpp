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

// Enough lines to pass LOG_MAX_BYTES; the last one is "last".
void Fill(BoundedLog& log) {
    const std::string line(999, 'x');
    for (uintmax_t written = 0; written <= LOG_MAX_BYTES; written += line.size() + 1) log.Write(line);
    log.Write("last");
}

// DESIGN「定数」: 1MB x 2 generations. broker.log goes to broker.prev.log when full.
void RotatingLogKeepsTwoGenerations(const fs::path& dir) {
    BoundedLog log(dir / "broker.log", dir / "broker.prev.log", false);
    Fill(log);
    assert(fs::file_size(dir / "broker.prev.log") > LOG_MAX_BYTES);
    assert(Read(dir / "broker.log") == "last\n");
}

// engine.log: the last run's log goes to engine.prev.log at a start; a full one drops its older half.
void TrimmingLogDropsItsOlderHalf(const fs::path& dir) {
    Write(dir / "engine.log", "the last run\n");
    BoundedLog log(dir / "engine.log", dir / "engine.prev.log", true);
    log.Rotate();
    assert(Read(dir / "engine.prev.log") == "the last run\n");
    Fill(log);
    const std::string kept = Read(dir / "engine.log");
    const std::string mark = "[earlier lines dropped: the log is kept under 1 MB]\n";
    assert(kept.size() <= LOG_MAX_BYTES && kept.size() > LOG_MAX_BYTES / 2 - 1000);
    assert(kept.compare(0, mark.size(), mark) == 0);
    assert(kept.compare(mark.size(), 1000, std::string(999, 'x') + "\n") == 0);  // from a line start
    assert(kept.compare(kept.size() - 5, 5, "last\n") == 0);
    assert(Read(dir / "engine.prev.log") == "the last run\n");
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
    TrimmingLogDropsItsOlderHalf(dir);
    StopsAreRecordedForTheManagementWindow(dir);
    EngineConfigIsRead(dir);
    fs::remove_all(dir);
    std::puts("support_test: all passed");
    return 0;
}

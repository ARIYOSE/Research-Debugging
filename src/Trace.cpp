#include "Trace.h"
#include <filesystem>
#include <fstream>

namespace {
    std::ofstream g_out;
    uint32_t g_frame = 0;
}

namespace Trace {

    void open(const std::string& path) {
        g_out.open(path);
        g_out << "frame,file,line,var,value,uses\n";
    }

    void close() { g_out.close(); }

    void setFrame(uint32_t frame) { g_frame = frame; }

    void def(const char* var, double value,
        std::initializer_list<const char*> uses,
        std::source_location loc) {
        if (!g_out.is_open()) return;

        std::string file = std::filesystem::path(loc.file_name()).filename().string();
        g_out << g_frame << ',' << file << ',' << loc.line() << ','
            << var << ',' << value << ',';

        bool first = true;
        for (const char* u : uses) {
            if (!first) g_out << ';';
            g_out << u;
            first = false;
        }
        g_out << '\n';
    }

} // namespace Trace
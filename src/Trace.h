#pragma once
#include <cstdint>
#include <initializer_list>
#include <source_location>
#include <string>

namespace Trace {
    void open(const std::string& path);
    void close();
    void setFrame(uint32_t frame);

    // var に value を書き込んだ。計算に uses の変数を使った。行番号は自動で記録される
    void def(const char* var, double value,
        std::initializer_list<const char*> uses,
        std::source_location loc = std::source_location::current());
}
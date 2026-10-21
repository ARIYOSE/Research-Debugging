#pragma once
#include <string>
#include <vector>
#include "Input.h"

namespace InputLog {
    // 入力列をファイルに書き出す。成功したら true
    bool save(const std::string& path, const std::vector<Input>& inputs);

    // ファイルから入力列を読み込む。成功したら true（失敗時は理由を表示）
    bool load(const std::string& path, std::vector<Input>& out);
}

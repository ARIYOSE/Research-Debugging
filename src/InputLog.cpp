#include "InputLog.h"
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <sstream>

namespace InputLog {

bool save(const std::string& path, const std::vector<Input>& inputs) {
    // 保存先のフォルダが無ければ作る
    std::filesystem::path p(path);
    if (p.has_parent_path()) {
        std::filesystem::create_directories(p.parent_path());
    }

    std::ofstream ofs(path);
    if (!ofs) {
        std::fprintf(stderr, "InputLog: cannot open '%s' for writing\n", path.c_str());
        return false;
    }

    ofs << "# platformer input log v1\n";
    ofs << "# frame left right jump\n";
    for (size_t f = 0; f < inputs.size(); ++f) {
        const Input& in = inputs[f];
        ofs << f << ' ' << in.left << ' ' << in.right << ' ' << in.jump << '\n';
    }
    return static_cast<bool>(ofs);
}

bool load(const std::string& path, std::vector<Input>& out) {
    std::ifstream ifs(path);
    if (!ifs) {
        std::fprintf(stderr, "InputLog: cannot open '%s'\n", path.c_str());
        return false;
    }

    out.clear();
    std::string line;
    int lineNo = 0;

    while (std::getline(ifs, line)) {
        ++lineNo;
        if (line.empty() || line[0] == '#') continue;   // 空行とコメントは飛ばす

        std::istringstream iss(line);
        size_t frame;
        int left, right, jump;
        if (!(iss >> frame >> left >> right >> jump)) {
            std::fprintf(stderr, "InputLog: parse error at line %d: '%s'\n",
                         lineNo, line.c_str());
            return false;
        }
        if (frame != out.size()) {
            std::fprintf(stderr, "InputLog: expected frame %zu but got %zu at line %d\n",
                         out.size(), frame, lineNo);
            return false;
        }
        out.push_back(Input{ left != 0, right != 0, jump != 0 });
    }
    return true;
}

} 
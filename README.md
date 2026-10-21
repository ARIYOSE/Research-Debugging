# Research-Debugging
## ビルド方法
必要なもの：CMake 3.20以上、C++17対応コンパイラ（MSVC または MinGW）

```
git clone https://github.com/ARIYOSE/Research-Debugging.git
cd Research-Debugging
cmake -S . -B build
cmake --build build --config Release
```
実行ファイルは `build/Release/` （MinGW の場合は `build/`）に生成されます。

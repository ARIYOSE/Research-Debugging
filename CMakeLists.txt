cmake_minimum_required(VERSION 3.22)
project(platformer_slice LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)          # std::source_location を使うため
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Box2D のサンプルやテストはビルドしない
set(BOX2D_SAMPLES OFF CACHE BOOL "" FORCE)
set(BOX2D_UNIT_TESTS OFF CACHE BOOL "" FORCE)
add_subdirectory(extern/box2d)

add_executable(platformer
    src/main.cpp
    #src/Game.cpp
    src/Player.cpp
    src/InputLog.cpp
    src/Trace.cpp
    #src/Render.cpp
)
target_link_libraries(platformer PRIVATE box2d)

if (MSVC)
    target_compile_options(platformer PRIVATE /utf-8)
endif()
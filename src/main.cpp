#include <box2d/box2d.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
#include <string>
#include "Player.h"
#include "Input.h"
#include "InputLog.h"
#include "Bug.h"
#include "Trace.h"

constexpr float kDt = 1.0f / 60.0f;
constexpr int   kSubSteps = 4;

// 台本：フレームごとの入力をまとめて作る
std::vector<Input> makeScriptedInputs(int frameCount) {
    std::vector<Input> inputs(frameCount);
    for (int f = 0; f < frameCount; ++f) {
        inputs[f].right = (f >= 30 && f < 200);
        inputs[f].jump  = (f >= 60 && f < 70);
    }
    return inputs;
}

const char* toString(JumpState s) {
    switch (s) {
        case JumpState::Grounded: return "Grounded";
        case JumpState::Rising:   return "Rising";
        case JumpState::Falling:  return "Falling";
    }
    return "?";
}

// float をビット単位でハッシュに混ぜる（FNV-1a）
uint64_t hashFloat(uint64_t h, float v) {
    uint32_t bits;
    std::memcpy(&bits, &v, sizeof(bits));
    for (int i = 0; i < 4; ++i) {
        h ^= (bits >> (8 * i)) & 0xFF;
        h *= 1099511628211ULL;
    }
    return h;
}

// 入力列を受け取ってシミュレーションを最後まで回す。戻り値は状態のハッシュ
uint64_t runSimulation(const std::vector<Input>& inputs) {
    b2WorldDef worldDef = b2DefaultWorldDef();
    worldDef.gravity = b2Vec2{ 0.0f, -10.0f };
    b2WorldId world = b2CreateWorld(&worldDef);

    // 地面
    b2BodyDef groundDef = b2DefaultBodyDef();
    groundDef.position = b2Vec2{ 0.0f, -1.0f };
    b2BodyId ground = b2CreateBody(world, &groundDef);
    b2Polygon groundBox = b2MakeBox(50.0f, 1.0f);
    b2ShapeDef groundShape = b2DefaultShapeDef();
    b2CreatePolygonShape(ground, &groundShape, &groundBox);

    // プレイヤー（動的な剛体、回転しないようにする）
    Player player;
    player.create(world, b2Vec2{0.0f, 0.8f});

    uint64_t hash = 1469598103934665603ULL;
    std::printf("frame,left,right,jump,x,y,vx,vy,grounded,state\n");

    const float dt = 1.0f / 60.0f;

    Trace::open(g_bug == 0 ? "trace_normal.csv" : "trace_bug" + std::to_string(g_bug) + ".csv");

    for (uint32_t frame = 0; frame < inputs.size(); ++frame) {
        const Input& in = inputs[frame];

        Trace::setFrame(frame);

        Trace::def("input.left", in.left, {});
        Trace::def("input.right", in.right, {});
        Trace::def("input.jump", in.jump, {});

        // ゲームプレイの更新：入力から速度を決める
        player.prePhysics(in);                    // ゲームプレイの更新
        b2World_Step(world, kDt, kSubSteps);      // 物理の更新（1フレームに1回だけ）

        b2Vec2 p = b2Body_GetPosition(player.body());
        b2Vec2 v = b2Body_GetLinearVelocity(player.body());

        Trace::def("player.x", p.x, { "player.x", "player.vx" });
        Trace::def("player.y", p.y, { "player.y", "player.vy" });
        Trace::def("player.vx", v.x, { "player.vx" });
        Trace::def("player.vy", v.y, { "player.vy", "player.y" });

        player.postPhysics();                     // 物理後の処理

        // 書式指定子 10 個 ↔ 引数 10 個
        std::printf("%u,%d,%d,%d,%.4f,%.4f,%.4f,%.4f,%d,%s\n",
                    frame,
                    in.left ? 1 : 0, in.right ? 1 : 0, in.jump ? 1 : 0,
                    p.x, p.y, v.x, v.y,
                    player.grounded() ? 1 : 0,
                    toString(player.state()));

        hash = hashFloat(hash, p.x);
        hash = hashFloat(hash, p.y);
        hash = hashFloat(hash, v.x);
        hash = hashFloat(hash, v.y);
        hash = hashFloat(hash, player.grounded() ? 1.0f : 0.0f);
        hash = hashFloat(hash, static_cast<float>(static_cast<int>(player.state())));
    }

    Trace::close();

    b2DestroyWorld(world);
    return hash;
}

int main(int argc, char** argv) {
    for (int i = 1; i + 1 < argc; ++i) {
        if (std::string(argv[i]) == "--bug") g_bug = std::stoi(argv[i + 1]);
    }

    std::string mode = (argc >= 2) ? argv[1] : "";
    std::vector<Input> inputs;

    if (mode == "replay" && argc >= 3) {
        if (!InputLog::load(argv[2], inputs)) return 1;
    } else {
        inputs = makeScriptedInputs(240);
        if (mode == "record" && argc >= 3) {
            if (!InputLog::save(argv[2], inputs)) return 1;
        }
    }

    uint64_t hash = runSimulation(inputs);

    // CSV と混ざらないよう、ハッシュは標準エラー出力に出す
    std::fprintf(stderr, "bug=%d frames=%zu hash=%016llx\n",
        g_bug, inputs.size(), static_cast<unsigned long long>(hash));
    return 0;
}
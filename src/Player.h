#pragma once
#include <box2d/box2d.h>
#include "Input.h"

enum class JumpState { Grounded, Rising, Falling };

class Player {
public:
    void create(b2WorldId world, b2Vec2 spawn);
    void prePhysics(const Input& in);   // 物理の前：入力から速度を決める
    void postPhysics();                 // 物理の後：接地判定と状態の更新

    b2BodyId body() const { return body_; }
    bool grounded() const { return grounded_; }
    JumpState state() const { return state_; }

private:
    bool checkGrounded() const;

    b2BodyId body_{};
    bool grounded_ = false;          // 足元が何かに接しているか
    bool prevJump_ = false;          // 前フレームのジャンプボタン（押した瞬間の判定用）
    JumpState state_ = JumpState::Falling;
    JumpState prevState_ = JumpState::Falling;
    int landingLag_ = 0;
    static constexpr float kMoveSpeed = 5.0f;
    static constexpr float kJumpSpeed = 7.0f;
};
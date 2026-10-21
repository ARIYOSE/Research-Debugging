#include "Player.h"
#include "Bug.h"
#include "Trace.h"

//変数を簡易的に記録
void Player::create(b2WorldId world, b2Vec2 spawn) {
    b2BodyDef def = b2DefaultBodyDef();
    def.type = b2_dynamicBody;
    def.position = spawn;
    def.motionLocks.angularZ = true;        // プレイヤーは回転させない
    body_ = b2CreateBody(world, &def);

    b2Polygon box = b2MakeBox(0.4f, 0.8f);
    b2ShapeDef shape = b2DefaultShapeDef();
    shape.density = 1.0f;
    b2CreatePolygonShape(body_, &shape, &box);
}

void Player::prePhysics(const Input& in) {
    b2Vec2 v = b2Body_GetLinearVelocity(body_);

    // 左右移動
    v.x = (static_cast<int>(in.right) - static_cast<int>(in.left)) * kMoveSpeed;
    Trace::def("player.vx", v.x, { "input.left", "input.right" });

    if (landingLag_ > 0) {
        v.x = 0.0f;                                   // 着地硬直中は横に動かない
        Trace::def("player.vx", v.x, { "player.landingLag" });
        --landingLag_;
        Trace::def("player.landingLag", landingLag_, { "player.landingLag" });
    }

    // ジャンプ：ボタンを押した瞬間、かつ地上にいるときだけ
    bool jumpPressed = in.jump && !prevJump_;
    Trace::def("jumpPressed", jumpPressed, { "input.jump", "player.prevJump" });

    if (jumpPressed && grounded_ && state_ == JumpState::Grounded) {
        v.y = kJumpSpeed;
        Trace::def("player.vy", v.y, { "jumpPressed", "player.grounded", "player.state" });
        state_ = JumpState::Rising;
        Trace::def("player.state", static_cast<int>(state_),
            { "jumpPressed", "player.grounded", "player.state" });
    }
    prevJump_ = in.jump;
    Trace::def("player.prevJump", prevJump_, { "input.jump" });

    b2Body_SetLinearVelocity(body_, v);
}

void Player::postPhysics() {
    bool onGround = checkGrounded();
    Trace::def("onGround", onGround, { "player.x", "player.y" });

    if (BUG(1)) {
        if (onGround) {
            grounded_ = true;   // バグ1：地面から離れても false に戻さない
            Trace::def("player.grounded", grounded_, { "onGround" });
        }
    }
    else {
        grounded_ = onGround;
        Trace::def("player.grounded", grounded_, { "onGround" });
    }

    float vy = b2Body_GetLinearVelocity(body_).y;

    if (grounded_ && vy <= 0.01f) state_ = JumpState::Grounded;
    else if (vy > 0.01f)          state_ = JumpState::Rising;
    else                          state_ = JumpState::Falling;
    Trace::def("player.state", static_cast<int>(state_), { "player.grounded", "player.vy" });
    //着地の瞬間か検知
    bool landed = (prevState_ != JumpState::Grounded && state_ == JumpState::Grounded);
    if (landed && !BUG(2)) {                          // バグ2：着地硬直の設定を忘れる
        landingLag_ = 10;
        Trace::def("player.landingLag", landingLag_, { "player.state", "player.prevState" });
    }
    prevState_ = state_;
    Trace::def("player.prevState", static_cast<int>(prevState_), { "player.state" });
}

bool Player::checkGrounded() const {
    b2ContactData contacts[8];
    int count = b2Body_GetContactData(body_, contacts, 8);

    for (int i = 0; i < count; ++i) {
        const b2ContactData& c = contacts[i];
        if (c.manifold.pointCount == 0) continue;

        // 法線は形状Aから形状Bへの向き。自分がAなら反転して「相手から自分へ」の向きにそろえる
        float ny = c.manifold.normal.y;
        b2BodyId a = b2Shape_GetBody(c.shapeIdA);
        if (B2_ID_EQUALS(a, body_)) ny = -ny;

        if (ny > 0.7f) return true;   // 相手から上向きに押されている＝足元に接している
    }
    return false;
}
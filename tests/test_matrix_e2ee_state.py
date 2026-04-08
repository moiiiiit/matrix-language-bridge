"""LanguageBridge E2EE state store helpers (no python-olm required)."""

import pytest
from mautrix.types import Member, Membership, RoomID, UserID

from languagebridge.matrix_e2ee import LanguageBridgeStateStore


@pytest.mark.asyncio
async def test_find_shared_rooms_only_encrypted_joined() -> None:
    store = LanguageBridgeStateStore()
    enc_room = RoomID("!e:matrix.org")
    plain_room = RoomID("!p:matrix.org")
    u_alice = UserID("@alice:matrix.org")
    u_bob = UserID("@bob:matrix.org")

    await store.set_member(enc_room, u_alice, Member(membership=Membership.JOIN))
    await store.set_member(enc_room, u_bob, Member(membership=Membership.JOIN))
    await store.set_encryption_info(enc_room, {"algorithm": "m.megolm.v1.aes-sha2"})

    await store.set_member(plain_room, u_alice, Member(membership=Membership.JOIN))

    alice_shared = await store.find_shared_rooms(u_alice)
    bob_shared = await store.find_shared_rooms(u_bob)

    assert enc_room in alice_shared
    assert plain_room not in alice_shared
    assert enc_room in bob_shared
    assert len(bob_shared) == 1

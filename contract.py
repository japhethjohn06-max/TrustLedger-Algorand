from algopy import *

class TransparencyApp(ARC4Contract):

    def __init__(self) -> None:
        # Initializing the key players
        self.student_rep = Global.creator_address
        self.admin = Global.creator_address  # VC / Authority

        # Governance rules
        self.approvals_required = UInt64(2)
        self.expense_count = UInt64(0)

        # Budget tracking
        self.total_deposited = UInt64(0)
        self.total_spent = UInt64(0)

        # Emergency pause: 0 = active, 1 = paused
        self.is_paused = UInt64(0)

    # ---------------------------
    # ADMIN: Deposit funds
    # ---------------------------
    @arc4.abimethod
    def deposit(self, amount: UInt64) -> None:
        assert Txn.sender == self.admin
        self.total_deposited += amount

    # ---------------------------
    # ADMIN: Pause / Unpause
    # ---------------------------
    @arc4.abimethod
    def set_pause(self, pause: UInt64) -> None:
        assert Txn.sender == self.admin
        self.is_paused = pause

    # ---------------------------
    # ADMIN: Add approver
    # ---------------------------
    @arc4.abimethod
    def add_approver(self, approver: Address) -> None:
        assert Txn.sender == self.admin
        key = Concat(Bytes("approver_"), approver.bytes)
        App.box_put(key, Bytes("1"))

    def is_approver(self, addr: Address) -> bool:
        key = Concat(Bytes("approver_"), addr.bytes)
        _, exists = App.box_get(key)
        return exists

    def remaining_balance(self) -> UInt64:
        return self.total_deposited - self.total_spent

    # ---------------------------
    # STEP 1: PROPOSE
    # ---------------------------
    @arc4.abimethod
    def propose_expense(
        self,
        amount: UInt64,
        description: String,
        ipfs_cid: String
    ) -> UInt64:

        assert self.is_paused == UInt64(0), "System is paused"
        assert Txn.sender == self.student_rep, "Only Student Rep"
        assert amount <= self.remaining_balance(), "Insufficient funds"

        # ✅ Prevent delimiter corruption
        assert Bytes("|") not in description.bytes, "Invalid character in description"
        assert Bytes("|") not in ipfs_cid.bytes, "Invalid character in CID"

        proposal_id = self.expense_count
        key = Concat(Bytes("proposal_"), Itob(proposal_id))

        # amount|description|cid|timestamp|approvals
        data = Concat(
            Itob(amount), Bytes("|"),
            description.bytes, Bytes("|"),
            ipfs_cid.bytes, Bytes("|"),
            Itob(Global.latest_timestamp), Bytes("|"),
            Itob(UInt64(0))
        )

        App.box_put(key, data)
        return proposal_id

    # ---------------------------
    # STEP 2: APPROVE
    # ---------------------------
    @arc4.abimethod
    def approve_expense(self, proposal_id: UInt64) -> None:

        assert self.is_paused == UInt64(0), "System paused"
        assert self.is_approver(Txn.sender), "Not an approver"

        proposal_key = Concat(Bytes("proposal_"), Itob(proposal_id))
        data, exists = App.box_get(proposal_key)
        assert exists, "Proposal not found"

        # Prevent double voting
        vote_key = Concat(Bytes("vote_"), Itob(proposal_id), Txn.sender.bytes)
        _, voted = App.box_get(vote_key)
        assert not voted, "Already approved"

        App.box_put(vote_key, Bytes("1"))

        # ✅ Safe parsing
        parts = data.split(Bytes("|"), 5)

        amount = parts[0]
        description = parts[1]
        cid = parts[2]
        timestamp = parts[3]
        approval_count = Btoi(parts[4]) + UInt64(1)

        # ✅ Expiry check (7 days)
        assert Global.latest_timestamp <= Btoi(timestamp) + UInt64(604800), "Proposal expired"

        # Update proposal
        updated = Concat(
            amount, Bytes("|"),
            description, Bytes("|"),
            cid, Bytes("|"),
            timestamp, Bytes("|"),
            Itob(approval_count)
        )

        App.box_put(proposal_key, updated)

        # ---------------------------
        # FINALIZE
        # ---------------------------
        if approval_count >= self.approvals_required:

            expense_key = Concat(Bytes("expense_"), Itob(proposal_id))

            # Immutable record
            App.box_put(expense_key, updated)

            # Update spending
            self.total_spent += Btoi(amount)

            self.expense_count += UInt64(1)

    # ---------------------------
    # VIEW FINALIZED EXPENSE
    # ---------------------------
    @arc4.abimethod
    def get_expense(self, expense_id: UInt64) -> Bytes:
        key = Concat(Bytes("expense_"), Itob(expense_id))
        value, exists = App.box_get(key)
        assert exists, "Expense not found"
        return value

    # ---------------------------
    # VIEW PROPOSAL
    # ---------------------------
    @arc4.abimethod
    def get_proposal(self, proposal_id: UInt64) -> Bytes:
        key = Concat(Bytes("proposal_"), Itob(proposal_id))
        value, exists = App.box_get(key)
        assert exists, "Proposal not found"
        return value

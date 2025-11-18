# app.py
import os
import sys
import time
from web3 import Web3
from typing import Dict, Any 
# new lines
def safe_rpc_call(func, *args, retries=3, delay=1):
    """Retry wrapper for transient RPC errors."""
    for attempt in range(1, retries + 1):
        try:
            return func(*args)
        except Exception as e:
            print(f"⚠️  RPC call failed (attempt {attempt}/{retries}): {e}")
            time.sleep(delay)
    print("❌ All RPC retries failed.")
    sys.exit(2)
    
# Config: set via env or edit directly
DEFAULT_RPC = "https://mainnet.infura.io/v3/your_api_key"
RPC_URL = os.getenv("RPC_URL", DEFAULT_RPC)

RPC_URL_2 = os.getenv("RPC_URL_2")  # optional second provider for cross-checks

NETWORKS = {
    1: "Ethereum Mainnet",
    11155111: "Sepolia Testnet",
    10: "Optimism",
    137: "Polygon",
    42161: "Arbitrum One",
}

def network_name(chain_id: int) -> str:
    return NETWORKS.get(chain_id, f"Unknown (chain ID {chain_id})")

def w3_connect(url: str) -> Web3:
    w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        print(f"❌ RPC connection failed: {url}")
        sys.exit(1)
    return w3

def parse_tx_hash(h: str) -> str:
    h = h.strip()
    if not h.startswith("0x"):
        h = "0x" + h
    if len(h) != 66 or not Web3.is_hex(h):
        print("❌ Invalid transaction hash. Expected 0x + 64 hex characters.")
        sys.exit(1)
    return h


def build_commitment(chain_id: int, tx_hash_hex: str, block_number: int, status: int, gas_used: int) -> str:
    # keccak(chainId[8] || txHash[32] || blockNumber[8] || status[1] || gasUsed[8])
    payload = (
        chain_id.to_bytes(8, "big")
        + bytes.fromhex(tx_hash_hex[2:])
        + block_number.to_bytes(8, "big")
        + status.to_bytes(1, "big")
        + gas_used.to_bytes(8, "big")
    )
    return "0x" + Web3.keccak(payload).hex()

def fetch_receipt_bundle(w3: Web3, txh: str) -> Dict[str, Any]:
    try:
        rcpt = safe_rpc_call(w3.eth.get_transaction_receipt, txh)
tx = safe_rpc_call(w3.eth.get_transaction, txh)
    except Exception as e:
        print(f"❌ Failed to fetch receipt: {e}")
        sys.exit(2)
    if rcpt is None:
        print("❌ Receipt not found (transaction pending or unknown).")
        sys.exit(2)
    status = int(rcpt.status)
    gas_used = int(rcpt.gasUsed)
    effective_gas_price = getattr(rcpt, "effectiveGasPrice", None)
    if effective_gas_price is None:
        # Legacy tx or provider doesn’t expose effectiveGasPrice
        effective_gas_price = tx.get("gasPrice")
    total_fee_wei = gas_used * int(effective_gas_price) if effective_gas_price is not None else None

    block_number = int(rcpt.blockNumber)
    # ✅ New lines to show block timestamp
block = w3.eth.get_block(rcpt.blockNumber)
print(f"🕒 Block timestamp: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(block.timestamp))} UTC")
    return {
                "gas_used": gas_used,
        "total_fee_eth": Web3.from_wei(total_fee_wei, "ether") if total_fee_wei is not None else None,
        "commitment": build_commitment(chain_id, txh, block_number, status, gas_used),
        "chain_id": w3.eth.chain_id,
        "network": network_name(w3.eth.chain_id),
        "tx_hash": txh,
        "block_number": block_number,
        "status": status,
        "gas_used": gas_used,
        "commitment": build_commitment(w3.eth.chain_id, txh, block_number, status, gas_used),
    }

def print_bundle(label: str, bundle: dict):
    print(f"— {label} —")
    print(f"🌐 Network: {bundle['network']} (chainId {bundle['chain_id']})")
    print(f"🔗 Tx: {bundle['tx_hash']}")
    print(f"👤 From: {bundle.get('from')}")
    print(f"📥 To:   {bundle.get('to')}")
    print(f"🔢 Block: {bundle['block_number']}")
    print(f"📦 Status: {bundle['status']}  GasUsed: {bundle['gas_used']}")
    print(f"🧩 Soundness Commitment: {bundle['commitment']}")


def main():
       if len(sys.argv) != 2:
        print("Usage: python app.py <tx_hash>")
        print("Example:")
        print("  RPC_URL=https://mainnet.infura.io/v3/YOUR_KEY python app.py 0xdeadbeef...")
        sys.exit(1)


    tx_hash = parse_tx_hash(sys.argv[1])

    start = time.time()
    w3 = w3_connect(RPC_URL)
        if RPC_URL == DEFAULT_RPC:
        print("⚠️  Using default RPC_URL placeholder; set RPC_URL env var for real usage.")
    primary = fetch_receipt_bundle(w3, tx_hash)
    print_bundle("PRIMARY", primary)
        if not RPC_URL_2:
        print("ℹ️  Set RPC_URL_2 to enable cross-provider soundness checks.")


       if RPC_URL_2:
        print(f"Connecting to secondary RPC: {RPC_URL_2}")
        w3b = w3_connect(RPC_URL_2)
        secondary = fetch_receipt_bundle(w3b, tx_hash)
        print_bundle("SECONDARY", secondary)
        print("— Cross-check —")
        same_chain = primary["chain_id"] == secondary["chain_id"]
        same_block = primary["block_number"] == secondary["block_number"]
        same_status = primary["status"] == secondary["status"]
        same_gas = primary["gas_used"] == secondary["gas_used"]
        same_commit = primary["commitment"] == secondary["commitment"]
        print(f"Chain IDs match: {'✅' if same_chain else '❌'}")
        print(f"Block numbers match: {'✅' if same_block else '❌'}")
        print(f"Status matches: {'✅' if same_status else '❌'}")
        print(f"GasUsed matches: {'✅' if same_gas else '❌'}")
        print(f"Commitments match: {'✅' if same_commit else '❌'}")
        if all([same_chain, same_block, same_status, same_gas, same_commit]):
            print("🔒 Soundness confirmed across providers.")
        else:
            print("⚠️  Inconsistency detected — check providers, tags, or re-run.")

      elapsed = time.time() - start
    if elapsed < 1:
        print(f"⏱️  Elapsed: {elapsed * 1000:.0f}ms")
    else:
        print(f"⏱️  Elapsed: {elapsed:.2f}s")


if __name__ == "__main__":
    sys.exit(main())


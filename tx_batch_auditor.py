import os
import sys
import time
import json
import argparse
from typing import List, Dict, Any, Optional

from web3 import Web3

DEFAULT_RPC_1 = os.getenv("RPC_URL", "https://mainnet.infura.io/v3/your_api_key")
DEFAULT_RPC_2 = os.getenv("RPC_URL_2")

NETWORKS = {
    1: "Ethereum Mainnet",
    11155111: "Sepolia Testnet",
    10: "Optimism",
    137: "Polygon",
    42161: "Arbitrum One",
}


def network_name(cid: int) -> str:
    return NETWORKS.get(cid, f"Unknown (chain ID {cid})")


def connect(rpc: str, label: str) -> Web3:
    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 20}))
    if not w3.is_connected():
        print(f"❌ Failed to connect to {label} RPC: {rpc}", file=sys.stderr)
        sys.exit(1)
    # Optional PoA middleware for some L2 / testnets
    try:
        from web3.middleware import geth_poa_middleware
        w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    except Exception:
        pass
    return w3


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Batch soundness checker for multiple Ethereum transaction receipts.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--rpc1",
        default=DEFAULT_RPC_1,
        help="Primary RPC URL (default from RPC_URL env)",
    )
    p.add_argument(
        "--rpc2",
        default=DEFAULT_RPC_2,
        help="Optional secondary RPC URL for cross-checks (default from RPC_URL_2 env)",
    )
    p.add_argument(
        "--file",
        help="File with one transaction hash (0x...) per line",
    )
    p.add_argument(
        "txs",
        nargs="*",
        help="Transaction hashes (0x...) to audit, if --file not used",
    )
    p.add_argument(
        "--max",
        type=int,
        default=0,
        help="Optional max number of transactions to process (0 = no limit)",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Print JSON instead of human-readable table",
    )
    return p.parse_args()


def read_hashes_from_file(path: str) -> List[str]:
    out: List[str] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                out.append(s)
    except FileNotFoundError:
        print(f"❌ File not found: {path}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"❌ Failed to read file {path}: {e}", file=sys.stderr)
        sys.exit(1)
    return out


def validate_tx_hash(h: str) -> bool:
    if not h.startswith("0x") or len(h) != 66:
        return False
    try:
        int(h[2:], 16)
    except ValueError:
        return False
    return True


def build_commitment(
    w3: Web3,
    tx_hash: str,
) -> Dict[str, Any]:
    """
    Compute commitment:
      keccak(chainId[8] || txHash[32] || blockNumber[8] || status[1] || gasUsed[8])
    Returns a dict with chainId, blockNumber, status, gasUsed, and hex commitment.
    """
    rcpt = w3.eth.get_transaction_receipt(tx_hash)
    chain_id = int(w3.eth.chain_id)
    block_number = int(rcpt.blockNumber)
    status = int(rcpt.status)
    gas_used = int(rcpt.gasUsed)

    # Encode components
    chain_bytes = chain_id.to_bytes(8, "big", signed=False)
    tx_bytes = bytes.fromhex(tx_hash[2:])
    block_bytes = block_number.to_bytes(8, "big", signed=False)
    status_bytes = status.to_bytes(1, "big", signed=False)
    gas_bytes = gas_used.to_bytes(8, "big", signed=False)

    preimage = chain_bytes + tx_bytes + block_bytes + status_bytes + gas_bytes
    commit = w3.keccak(preimage)

    return {
        "chainId": chain_id,
        "blockNumber": block_number,
        "status": status,
        "gasUsed": gas_used,
        "commitment": commit.hex(),
    }


def audit_tx(
    tx_hash: str,
    w3_primary: Web3,
    w3_secondary: Optional[Web3],
) -> Dict[str, Any]:
    start = time.time()
    result: Dict[str, Any] = {
        "txHash": tx_hash,
        "primary": None,
        "secondary": None,
        "match": None,
        "errorPrimary": None,
        "errorSecondary": None,
        "timingSec": None,
    }

    # Primary
    try:
        primary = build_commitment(w3_primary, tx_hash)
        result["primary"] = primary
    except Exception as e:
        result["errorPrimary"] = str(e)

    # Secondary (optional)
    if w3_secondary is not None:
        try:
            secondary = build_commitment(w3_secondary, tx_hash)
            result["secondary"] = secondary
        except Exception as e:
            result["errorSecondary"] = str(e)

    # Compare if both succeeded
    if result["primary"] and result["secondary"]:
        result["match"] = (
            result["primary"]["commitment"] == result["secondary"]["commitment"]
        )

    result["timingSec"] = round(time.time() - start, 3)
    return result


def main() -> None:
    args = parse_args()

    # Gather tx hashes
    if args.file:
        hashes = read_hashes_from_file(args.file)
    else:
        hashes = list(args.txs)

    # Simple validation & dedup
    hashes = [h.strip() for h in hashes if h.strip()]
    hashes = list(dict.fromkeys(hashes))  # preserve order, remove dups

    if not hashes:
        print("⚠️  No transaction hashes provided. Use --file or positional tx hashes.", file=sys.stderr)
        sys.exit(1)

    bad = [h for h in hashes if not validate_tx_hash(h)]
    if bad:
        print("❌ Invalid transaction hash(es):", file=sys.stderr)
        for h in bad:
            print(f"   - {h}", file=sys.stderr)
        sys.exit(1)

    if args.max > 0 and len(hashes) > args.max:
        hashes = hashes[: args.max]

    # Connections
    if "your_api_key" in args.rpc1:
        print(
            "⚠️  Primary RPC still uses placeholder 'your_api_key'. "
            "Did you configure RPC_URL?",
            file=sys.stderr,
        )

    w3_primary = connect(args.rpc1, "primary")
    w3_secondary: Optional[Web3] = None
    if args.rpc2:
        w3_secondary = connect(args.rpc2, "secondary")
            if w3_secondary is not None:
        if int(w3_primary.eth.chain_id) != int(w3_secondary.eth.chain_id):
            print(
                f"❌ chainId mismatch between primary ({w3_primary.eth.chain_id}) "
                f"and secondary ({w3_secondary.eth.chain_id}) RPCs.",
                file=sys.stderr,
            )
            sys.exit(1)


    t0 = time.time()
    results: List[Dict[str, Any]] = []

    for h in hashes:
        res = audit_tx(h, w3_primary, w3_secondary)
        results.append(res)

    elapsed = round(time.time() - t0, 3)

    if args.json:
        payload = {
            "primary": {
                "rpc": args.rpc1,
                "chainId": int(w3_primary.eth.chain_id),
                "network": network_name(int(w3_primary.eth.chain_id)),
            },
            "secondary": (
                {
                    "rpc": args.rpc2,
                    "chainId": int(w3_secondary.eth.chain_id),  # type: ignore[arg-type]
                    "network": network_name(int(w3_secondary.eth.chain_id)),  # type: ignore[arg-type]
                }
                if w3_secondary is not None
                else None
            ),
            "elapsedSec": elapsed,
            "results": results,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    # Human-readable summary
    print(
        f"🌐 Primary: {network_name(int(w3_primary.eth.chain_id))} "
        f"(chainId {w3_primary.eth.chain_id})"
    )
    if w3_secondary is not None:
        print(
            f"🌐 Secondary: {network_name(int(w3_secondary.eth.chain_id))} "
            f"(chainId {w3_secondary.eth.chain_id})"
        )
    print(f"🧮 Auditing {len(results)} transaction(s) in {elapsed}s\n")

    for res in results:
        print(f"🔗 {res['txHash']}")
        if res["errorPrimary"]:
            print(f"   ❌ Primary error: {res['errorPrimary']}")
            continue

        p = res["primary"]
        print(
            f"   🧱 block={p['blockNumber']}  status={p['status']}  "
            f"gasUsed={p['gasUsed']}  chainId={p['chainId']}"
        )
        print(f"   🔐 commitment (primary): {p['commitment']}")

        if w3_secondary is not None:
            if res["errorSecondary"]:
                print(f"   ⚠️ Secondary error: {res['errorSecondary']}")
            elif res["secondary"]:
                s = res["secondary"]
                tag = "✅ MATCH" if res["match"] else "❌ MISMATCH"
                print(f"   🔐 commitment (secondary): {s['commitment']}  [{tag}]")

        print(f"   ⏱️  per-tx time: {res['timingSec']}s\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Aborted by user.", file=sys.stderr)
        sys.exit(1)

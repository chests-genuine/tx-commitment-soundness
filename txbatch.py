import argparse
import os
import sys
import time
from typing import Dict, List, Optional, Any

from web3 import Web3
from web3.exceptions import TransactionNotFound
VERSION = "0.1.0"

# Config: RPCs come from the environment, like txapp.py
DEFAULT_RPC = "https://mainnet.infura.io/v3/your_api_key"
RPC_URL = os.getenv("RPC_URL", DEFAULT_RPC)
RPC_URL_2 = os.getenv("RPC_URL_2")  # optional secondary provider

NETWORKS: Dict[int, str] = {
    1: "Ethereum Mainnet",
    11155111: "Sepolia Testnet",
    10: "Optimism",
    137: "Polygon",
    42161: "Arbitrum One",
}


def network_name(chain_id: int) -> str:
    return NETWORKS.get(chain_id, f"Unknown (chain ID {chain_id})")


def safe_rpc_call(func, *args, retries: int = 3, delay: float = 1.0):
    """Retry wrapper for transient RPC errors."""
    for attempt in range(1, retries + 1):
        try:
            return func(*args)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            if attempt == retries:
                print(f"❌ RPC call failed after {retries} attempts: {e}", file=sys.stderr)
                raise
            print(f"⚠️  RPC call failed (attempt {attempt}/{retries}): {e}", file=sys.stderr)
            time.sleep(delay)


def w3_connect(url: str) -> Web3:
    """Create a Web3 HTTP provider and exit if the connection fails."""
    w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        print(f"❌ RPC connection failed: {url}", file=sys.stderr)
        sys.exit(1)
    return w3


def parse_tx_hash(h: str) -> Optional[str]:
    """Normalize and validate a tx hash string."""
    h = h.strip()
    if not h:
        return None
    if not h.startswith("0x"):
        h = "0x" + h
    if len(h) != 66 or not Web3.is_hex(h):
        return None
    return h


def build_commitment(
    chain_id: int,
    tx_hash_hex: str,
    block_number: int,
    status: int,
    gas_used: int,
) -> str:
    """
    keccak(chainId[8] || txHash[32] || blockNumber[8] || status[1] || gasUsed[8])
    """
    payload = (
        chain_id.to_bytes(8, "big")
        + bytes.fromhex(tx_hash_hex[2:])
        + block_number.to_bytes(8, "big")
        + status.to_bytes(1, "big")
        + gas_used.to_bytes(8, "big")
    )
    return "0x" + Web3.keccak(payload).hex()


def fetch_bundle(w3: Web3, txh: str) -> Dict[str, Any]:
    """Fetch tx + receipt and compute the commitment."""
    try:
        rcpt = safe_rpc_call(w3.eth.get_transaction_receipt, txh)
        tx = safe_rpc_call(w3.eth.get_transaction, txh)
    except TransactionNotFound:
        raise
    except Exception as e:
        print(f"❌ Failed to fetch transaction or receipt: {e}", file=sys.stderr)
        raise

    if rcpt is None:
        raise RuntimeError("receipt is None (tx pending or unknown)")

    chain_id = safe_rpc_call(lambda: w3.eth.chain_id)
    status = int(rcpt.status)
    gas_used = int(rcpt.gasUsed)
    block_number = int(rcpt.blockNumber)
    commitment = build_commitment(chain_id, txh, block_number, status, gas_used)

    # Compute total fee in ETH if possible (nice for batch overview)
    effective_gas_price = getattr(rcpt, "effectiveGasPrice", None)
    if effective_gas_price is None:
        effective_gas_price = tx.get("gasPrice")
    if effective_gas_price is not None:
        total_fee_wei = gas_used * int(effective_gas_price)
        total_fee_eth = float(Web3.from_wei(total_fee_wei, "ether"))
    else:
        total_fee_eth = None

    return {
        "chain_id": chain_id,
        "network": network_name(chain_id),
        "tx_hash": txh,
        "from": tx["from"],
        "to": tx["to"],
        "block_number": block_number,
        "status": status,
        "gas_used": gas_used,
        "total_fee_eth": total_fee_eth,
        "commitment": commitment,
    }


def load_hashes(args: argparse.Namespace) -> List[str]:
    """Collect tx hashes from --tx and/or --file, de-duped."""
    hashes: List[str] = []

    for h in args.tx:
        hashes.append(h)

    if args.file:
        if args.file == "-":
            fh = sys.stdin
        else:
            try:
                fh = open(args.file, "r", encoding="utf-8")
            except OSError as exc:
                print(f"❌ Failed to open file {args.file}: {exc}", file=sys.stderr)
                sys.exit(1)
        with fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                hashes.append(line)

    # Deduplicate while preserving order
    seen = set()
    unique: List[str] = []
    for h in hashes:
        if h not in seen:
            seen.add(h)
            unique.append(h)
    return unique


def build_parser() -> argparse.ArgumentParser:
        p.add_argument(
        "--version",
        action="store_true",
        help="Print version and exit",
    )

    p = argparse.ArgumentParser(
        description="Batch-check tx commitment soundness for multiple transactions.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--tx",
        action="append",
        default=[],
        help="Transaction hash (0x...). Can be specified multiple times.",
    )
    p.add_argument(
        "--file",
        help="Path to file with one tx hash per line (use '-' for stdin).",
    )
    p.add_argument(
        "--no-emoji",
        action="store_true",
        help="Disable emoji in output (useful for CI logs).",
    )
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.version:
        print(f"txbatch {VERSION}")
        return 0

    use_emoji = not args.no_emoji
    ok_icon = "✅" if use_emoji else "OK"
    err_icon = "❌" if use_emoji else "ERR"
    warn_icon = "⚠️ " if use_emoji else "WARN: "
    match_icon = "🔒" if use_emoji else "MATCH"
    mismatch_icon = "⚠️ " if use_emoji else "MISMATCH"

    if RPC_URL == DEFAULT_RPC:
        print(
            f"{warn_icon}Using default RPC URL placeholder. "
            "Set RPC_URL in your environment for real usage.",
            file=sys.stderr,
        )

    hashes_raw = load_hashes(args)
    if not hashes_raw:
        print(
            f"{err_icon} No transaction hashes provided (use --tx and/or --file).",
            file=sys.stderr,
        )
        parser.print_help()
        return 1

    # Normalize and filter hashes
    tx_hashes: List[str] = []
    invalid_count = 0
    for raw in hashes_raw:
        h = parse_tx_hash(raw)
        if h is None:
            print(f"{err_icon} invalid tx hash: {raw}", file=sys.stderr)
            invalid_count += 1
            continue
        tx_hashes.append(h)

    if not tx_hashes:
        print(f"{err_icon} No valid transaction hashes to process.", file=sys.stderr)
        return 1

    start = time.time()

    # Connect primary
    print(f"Connecting to primary RPC: {RPC_URL}")
    w3 = w3_connect(RPC_URL)
    primary_chain_id = safe_rpc_call(lambda: w3.eth.chain_id)
    print(
        f"{ok_icon} Primary: {network_name(primary_chain_id)} "
        f"(chainId {primary_chain_id})"
    )

    # Optional secondary
    w3b: Optional[Web3] = None
    if RPC_URL_2:
        print(f"Connecting to secondary RPC: {RPC_URL_2}")
        w3b = w3_connect(RPC_URL_2)
        secondary_chain_id = safe_rpc_call(lambda: w3b.eth.chain_id)
        print(
            f"{ok_icon} Secondary: {network_name(secondary_chain_id)} "
            f"(chainId {secondary_chain_id})"
        )

    print("\n# tx | status | chain | block | fee(ETH) | commitment | cross-check")

    success_count = 0
    fail_count = 0
    pending_count = 0
    not_found_count = 0
    mismatch_count = 0

    for txh in tx_hashes:
        try:
            bundle_primary = fetch_bundle(w3, txh)
        except TransactionNotFound:
            print(f"{err_icon} {txh} | not-found on primary RPC")
            not_found_count += 1
            continue
        except Exception as e:
            print(f"{err_icon} {txh} | error on primary RPC: {e}", file=sys.stderr)
            fail_count += 1
            continue

        status_str = "success" if bundle_primary["status"] == 1 else "failed"
        fee_str = (
            f"{bundle_primary['total_fee_eth']:.6f}"
            if bundle_primary["total_fee_eth"] is not None
            else "-"
        )

        cross_note = "-"
        match = True

        if w3b is not None:
            try:
                bundle_secondary = fetch_bundle(w3b, txh)
                same_chain = bundle_primary["chain_id"] == bundle_secondary["chain_id"]
                same_block = (
                    bundle_primary["block_number"] == bundle_secondary["block_number"]
                )
                same_status = (
                    bundle_primary["status"] == bundle_secondary["status"]
                )
                same_gas = (
                    bundle_primary["gas_used"] == bundle_secondary["gas_used"]
                )
                same_commit = (
                    bundle_primary["commitment"]
                    == bundle_secondary["commitment"]
                )

                if all([same_chain, same_block, same_status, same_gas, same_commit]):
                    cross_note = f"{match_icon} ok"
                else:
                    cross_note = f"{mismatch_icon} mismatch"
                    match = False
            except TransactionNotFound:
                cross_note = f"{warn_icon}not-found on secondary"
                match = False
            except Exception as e:
                cross_note = f"{warn_icon}error on secondary: {e}"
                match = False

        icon = ok_icon if bundle_primary["status"] == 1 else err_icon
        print(
            f"{icon} {txh} | {status_str} | "
            f"{bundle_primary['chain_id']} | "
            f"{bundle_primary['block_number']} | "
            f"{fee_str} | "
            f"{bundle_primary['commitment']} | "
            f"{cross_note}"
        )

        if bundle_primary["status"] == 1:
            success_count += 1
        else:
            fail_count += 1
        if not match and w3b is not None:
            mismatch_count += 1

    elapsed = time.time() - start
    elapsed_str = f"{elapsed * 1000:.0f}ms" if elapsed < 1 else f"{elapsed:.2f}s"

    print(
        f"\nProcessed {len(tx_hashes)} tx(s) "
        f"(invalid input hashes skipped: {invalid_count}) in {elapsed_str}."
    )
    print(
        f"Summary: success={success_count}, failed={fail_count}, "
        f"not_found={not_found_count}, pending={pending_count}, "
        f"cross_mismatches={mismatch_count}"
    )

    if mismatch_count > 0:
        print(
            f"{warn_icon}{mismatch_count} transaction(s) had cross-provider mismatches.",
            file=sys.stderr,
        )
        return 2 if w3b is not None else 0

    # Non-zero if we had serious problems
    if fail_count > 0 or not_found_count > 0 or invalid_count > 0:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

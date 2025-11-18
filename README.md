# README.md
# tx-commitment-soundness

## Overview
+This tool derives a deterministic commitment from on-chain transaction facts
+to help spot inconsistencies across providers.
+
+**Commitment fields** (conceptually):
+- `chainId`, `txHash`, `blockNumber`, `status`, `gasUsed`
+
+> If two honest providers return different commitments for the same tx,
+> something is off and deserves investigation (soundness check).
+
+## Quickstart
+```bash
+pip install web3
+export RPC_URL="https://mainnet.infura.io/v3/<KEY>"
+# optional second provider for cross-checks
+# export RPC_URL_2="https://rpc.ankr.com/eth"
+python app.py 0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
+```
+
## Files
- txapp.py — CLI tool that:
  - Connects to an Ethereum-compatible RPC
  - Loads the transaction receipt
  - Prints key fields and a soundness commitment
  - Optionally cross-verifies the result against a second RPC

## Requirements
- Python 3.10 or newer
- web3.py
- An Ethereum RPC endpoint (Infura, Alchemy, or your own node)
## Quickstart

### 1. Install dependencies
pip install web3

### 2. Set your RPC (e.g. Infura)
export RPC_URL="https://mainnet.infura.io/v3/YOUR_KEY"

### 3. Run the checker for a transaction
python txapp.py 0xYOUR_TX_HASH_HERE

## Install
1) Install dependencies:
   pip install web3
2) Configure RPC:
   * Primary: set environment variable `RPC_URL`, or edit `txapp.py` and replace `your_api_key`
   - Optional secondary for cross-checks: set RPC_URL_2

## Usage
   python app.py <tx_hash>
### Batch commitment checks

Use `txbatch.py` to check multiple transactions and their commitments in one run:

bash
RPC_URL=https://mainnet.infura.io/v3/YOUR_KEY \
python txbatch.py \
  --tx 0xaaa... \
  --tx 0xbbb...

# Or from a file (one hash per line)
RPC_URL=... \
python txbatch.py --file txhashes.txt   

## Example Output
When you run the tool, you’ll see output similar to this:
🌐 Network: Ethereum Mainnet (chainId 1)
🔗 Tx: 0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
👤 From: 0x742d35Cc6634C0532925a3b844Bc454e4438f44e
🎯 To: 0x00000000219ab540356cBB839Cbe05303d7705Fa
🔢 Block: 18945023
🕒 Block timestamp: 2025-11-09 14:26:13 UTC
📦 Status: 1 GasUsed: 64231
🧩 Soundness Commitment: 0x9cfd58c6e91e3f0fa2e2c178b02f5e8fdd58b72a4e27da9b82f442b31f6a0a9e
⏱️ Elapsed: 2.45s

If you configure two RPCs, an extra *Cross-check* section will appear showing whether results match between providers.


### What the script prints
- Network name and chain ID
- Transaction hash and block number
- Status (0 or 1) and gas used
- Soundness commitment: keccak(chainId[8] || txHash[32] || blockNumber[8] || status[1] || gasUsed[8])
- If RPC_URL_2 is set: a cross-check section comparing fields and commitments

### Why this is related to soundness and ZK
- Soundness means invalid statements cannot pass verification
- By committing to essential receipt fields, any mismatch across providers becomes obvious
- This pattern is similar to how zk-rollups commit to state roots and verify succinct proofs against those roots

## Notes
- Works on Mainnet, Sepolia, and other EVM chains; the commitment is deterministic for the same chain and receipt
- If your provider is non-archival and the tx is old, you might need a different RPC
- This is not a zero-knowledge proof; it is a commitment primitive you could later verify inside a ZK circuit for privacy-preserving checks
- For CI, set both RPC_URL and RPC_URL_2 to independent providers and assert that commitments match
### CI usage example

In CI (GitHub Actions, GitLab, etc.), you can run:

```bash
RPC_URL=https://mainnet.infura.io/v3/YOUR_KEY \
RPC_URL_2=https://rpc.ankr.com/eth \
python txapp.py 0xYOUR_TX_HASH_HERE

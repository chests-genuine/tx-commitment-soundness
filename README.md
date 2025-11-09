# README.md
# tx-commitment-soundness

## Overview
This tiny repo demonstrates a Web3-flavored soundness check for a single Ethereum transaction. It fetches the transaction receipt from an RPC endpoint and derives a commitment that binds chainId, txHash, blockNumber, status, and gasUsed. This mirrors how Aztec-style or rollup systems commit to facts so they cannot be forged without detection. Optionally, you can cross-check the same transaction against a second RPC to detect inconsistencies.

## Files
- app.py — CLI tool that:
  - Connects to an Ethereum-compatible RPC
  - Loads the transaction receipt
  - Prints key fields and a soundness commitment
  - Optionally cross-verifies the result against a second RPC

## Requirements
- Python 3.10 or newer
- web3.py
- An Ethereum RPC endpoint (Infura, Alchemy, or your own node)

## Install
1) Install dependencies:
   pip install web3
2) Configure RPC:
   - Primary: set environment variable RPC_URL, or edit app.py and replace your_api_key
   - Optional secondary for cross-checks: set RPC_URL_2

## Usage
   python app.py <tx_hash>

## Examples
   python app.py 0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
   RPC_URL_2=https://rpc.ankr.com/eth python app.py 0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa

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
- Set `RPC_URL` and (optionally) `RPC_URL_2` to independent RPC providers and assert commitments match.
- The script exits with codes: `0` = success, `1` = invalid input/setup, `2` = fetch/lookup error.

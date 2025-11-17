# app.py
"""
zk_fee_profiler — L1 gas fee profiler for ZK / soundness systems (Aztec, Zama, rollups).

This script samples recent Ethereum-style blocks via web3 and computes
percentiles for base fee and effective gas price to suggest "safe" gas
settings for ZK rollups or other soundness-critical transactions.
"""

import os
import sys
import time
import argparse
from statistics import median
from typing import List, Dict, Any

from web3 import Web3

DEFAULT_RPC = os.getenv("RPC_URL", "https://mainnet.infura.io/v3/your_api_key")
DEFAULT_BLOCKS = int(os.getenv("ZK_FEE_BLOCKS", "180"))
DEFAULT_STEP = int(os.getenv("ZK_FEE_STEP", "3"))
DEFAULT_TARGET_PCT = float(os.getenv("ZK_FEE_TARGET_PCT", "0.8"))  # 80% by default

NETWORKS: Dict[int, str] = {
    1: "Ethereum Mainnet",
    11155111: "Sepolia Testnet",
    10: "Optimism",
    137: "Polygon",
    42161: "Arbitrum One",
    8453: "Base",
}


def network_name(cid: int) -> str:
    return NETWORKS.get(cid, f"Unknown (chain ID {cid})")


def connect(rpc: str) -> Web3:
    start = time.time()
    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        print(f"❌ Failed to connect to RPC: {rpc}", file=sys.stderr)
        sys.exit(1)
    cid = int(w3.eth.chain_id)
    head = int(w3.eth.block_number)
    elapsed = time.time() - start
    print(f"🌐 Connected to {network_name(cid)} (chainId {cid}, tip={head}) in {elapsed:.2f}s")
    return w3


def pct(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    q = max(0.0, min(1.0, q))
    sorted_vals = sorted(values)
    idx = int(round(q * (len(sorted_vals) - 1)))
    return sorted_vals[idx]


def sample_block_fees(block: Any) -> Dict[str, float]:
    """
    Return simple block-level stats:
    - base_fee_gwei
    - median_effective_gwei (over txs that carry gas price info)
    - median_tip_gwei (approx priority fee)
    """
    base_fee_wei = int(getattr(block, "baseFeePerGas", block.get("baseFeePerGas", 0) or 0))
    base_fee_gwei = float(Web3.from_wei(base_fee_wei, "gwei"))

    effective_prices: List[float] = []
    tips: List[float] = []
    bf = base_fee_wei

    for tx in block.transactions:
        # tx may be AttributeDict or dict
        tx_type = tx.get("type", 0) if isinstance(tx, dict) else getattr(tx, "type", 0)

        if tx_type == 2:
            max_priority = int(tx.get("maxPriorityFeePerGas", 0)) if isinstance(tx, dict) else int(
                getattr(tx, "maxPriorityFeePerGas", 0)
            )
            max_fee = int(tx.get("maxFeePerGas", 0)) if isinstance(tx, dict) else int(
                getattr(tx, "maxFeePerGas", 0)
            )
            eff = min(max_fee, bf + max_priority)
            effective_prices.append(float(Web3.from_wei(eff, "gwei")))
            tips.append(float(Web3.from_wei(max_priority, "gwei")))
        else:
            gas_price = int(tx.get("gasPrice", 0)) if isinstance(tx, dict) else int(
                getattr(tx, "gasPrice", 0)
            )
            effective_prices.append(float(Web3.from_wei(gas_price, "gwei")))
            tip_wei = max(0, gas_price - bf)
            tips.append(float(Web3.from_wei(tip_wei, "gwei")))

    return {
        "base_fee_gwei": base_fee_gwei,
        "median_effective_gwei": median(effective_prices) if effective_prices else 0.0,
        "median_tip_gwei": median(tips) if tips else 0.0,
    }


def analyze_fees(
    w3: Web3,
    blocks: int,
    step: int,
    target_pct: float,
    head_override: int | None = None,
) -> Dict[str, Any]:
    head = int(head_override) if head_override is not None else int(w3.eth.block_number)
    start_block = max(0, head - blocks + 1)

    base_fees: List[float] = []
    effs: List[float] = []
    tips: List[float] = []

    print(f"🔍 Sampling last {blocks} blocks (every {step}th block) from head={head}...")
    t0 = time.time()
    sampled_blocks = 0

    for n in range(head, start_block - 1, -step):
        blk = w3.eth.get_block(n, full_transactions=True)
        sampled_blocks += 1
        stats = sample_block_fees(blk)
        base_fees.append(stats["base_fee_gwei"])
        if stats["median_effective_gwei"] > 0:
            effs.append(stats["median_effective_gwei"])
        if stats["median_tip_gwei"] > 0:
            tips.append(stats["median_tip_gwei"])

        if sampled_blocks % 20 == 0:
            print(f"   ⏳ At block {n} (sampled {sampled_blocks})...")

    elapsed = time.time() - t0

    base_p50 = median(base_fees) if base_fees else 0.0
    base_target = pct(base_fees, target_pct) if base_fees else 0.0

    tip_p50 = median(tips) if tips else 0.0
    tip_target = pct(tips, target_pct) if tips else 0.0

    recommended_tip = round(max(tip_p50, tip_target) * 1.2, 3)
    recommended_max_fee = round(base_target + recommended_tip, 3)

    cid = int(w3.eth.chain_id)

    return {
        "chainId": cid,
        "network": network_name(cid),
        "head": head,
        "sampledBlocks": sampled_blocks,
        "blockWindow": blocks,
        "step": step,
        "targetPercentile": target_pct,
        "timingSec": round(elapsed, 2),
        "baseFeeGwei": {
            "p50": round(base_p50, 3),
            "pTarget": round(base_target, 3),
            "min": round(min(base_fees), 3) if base_fees else 0.0,
            "max": round(max(base_fees), 3) if base_fees else 0.0,
        },
        "medianEffectivePriceGwei": round(median(effs), 3) if effs else 0.0,
        "medianTipGwei": {
            "p50": round(tip_p50, 3),
            "pTarget": round(tip_target, 3),
        },
        "recommendedForZK": {
            "maxPriorityFeeGwei": recommended_tip,
            "maxFeePerGasGwei": recommended_max_fee,
        },
    }


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Profile recent gas behavior for ZK / soundness systems and suggest EIP-1559 gas settings.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--rpc", default=DEFAULT_RPC, help="RPC URL (default from RPC_URL env)")
    ap.add_argument("-b", "--blocks", type=int, default=DEFAULT_BLOCKS, help="How many recent blocks to scan")
    ap.add_argument("-s", "--step", type=int, default=DEFAULT_STEP, help="Sample every Nth block for speed")
    ap.add_argument(
        "-p",
        "--percentile",
        type=float,
        default=DEFAULT_TARGET_PCT,
        help="Target percentile (0.0–1.0) for fee suggestions (e.g. 0.8 = 80%)",
    )
    ap.add_argument(
        "--head",
        type=int,
        help="Use this block number as head instead of latest",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="Output JSON only (for scripts / dashboards)",
    )
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    print(f"📅 Fee profiler started at UTC {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}")
    if args.blocks <= 0 or args.step <= 0:
        print("❌ --blocks and --step must be > 0", file=sys.stderr)
        sys.exit(1)

    w3 = connect(args.rpc)
    result = analyze_fees(w3, args.blocks, args.step, args.percentile, args.head)

    if args.json:
        import json

        payload = {
            "mode": "zk_fee_profile",
            "generatedAtUtc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
            "data": result,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        bf = result["baseFeeGwei"]
        tip = result["medianTipGwei"]
        rec = result["recommendedForZK"]

        print("")
        print(f"🌐 {result['network']} (chainId {result['chainId']})")
        print(f"📦 Head block: {result['head']}  window={result['blockWindow']}  step={result['step']}")
        print(f"📊 Sampled blocks: {result['sampledBlocks']} in {result['timingSec']}s")
        print(f"🎯 Target percentile: {result['targetPercentile'] * 100:.1f}%")
        print("")
        print(
            f"⛽ Base fee (Gwei):  p50={bf['p50']}  "
            f"pTarget={bf['pTarget']}  min={bf['min']}  max={bf['max']}"
        )
        print(
            f"🎁 Tip (Gwei):       p50={tip['p50']}  "
            f"pTarget={tip['pTarget']}"
        )
        print("")
        print("🔐 Suggested EIP-1559 settings for ZK / rollup / soundness-critical txs:")
        print(f"   maxPriorityFeePerGas ≈ {rec['maxPriorityFeeGwei']} Gwei")
        print(f"   maxFeePerGas         ≈ {rec['maxFeePerGasGwei']} Gwei")
        print("")
        print("ℹ️  Use these values as upper bounds in Aztec-style rollups, Zama-integrated flows,")
        print("   or any system where deterministic gas assumptions impact soundness guarantees.")

    print(f"\n✅ Done at UTC {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}")


if __name__ == "__main__":
    main()

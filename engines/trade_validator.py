"""
Trade Validator - Ensures all signals have valid SL and targets before sending.
"""

from typing import Dict, List, Tuple, Optional
from loguru import logger


class TradeValidator:
    """
    Validates stop loss and target levels for trading signals.

    Rules:
    - SL must be on opposite side of entry for direction
    - SL % risk: 1-5% (configurable)
    - At least 2 targets required
    - T1 R:R >= 1.5
    - T2 R:R >= 2.5
    - Targets should be sequentially increasing
    """

    def __init__(self, config: Dict = None):
        self.config = config or {}

        # Configurable thresholds
        self.min_risk_reward = self.config.get('min_risk_reward', 1.5)
        self.max_sl_pct = self.config.get('max_stop_loss_pct', 5.0)
        self.min_sl_pct = self.config.get('min_stop_loss_pct', 1.0)
        self.min_targets = self.config.get('min_targets', 2)
        self.min_score = self.config.get('min_signal_score', 60)

    def validate(self, signal: Dict, indicators: Dict) -> Dict:
        """
        Full validation of a signal.

        Args:
            signal: Signal dictionary with entry, SL, targets
            indicators: Technical indicators dictionary

        Returns:
            {'valid': bool, 'errors': []}
        """
        errors = []

        entry = signal.get('entry', signal.get('entry_zone_min', 0))
        sl = signal.get('stop_loss', 0)
        targets = signal.get('targets', signal.get('target_1', []))
        if not isinstance(targets, list):
            targets = [targets] if targets else []

        direction = signal.get('direction', 'LONG')

        # 1. Validate STOP LOSS
        sl_valid, sl_errors = self.validate_stop_loss(entry, sl, direction, indicators)
        errors.extend(sl_errors)

        # 2. Validate TARGETS
        t_valid, t_errors = self.validate_targets(entry, sl, targets, direction, indicators)
        errors.extend(t_errors)

        # 3. Validate R:R
        risk = abs(entry - sl)
        if risk > 0 and len(targets) > 0:
            t1_reward = abs(targets[0] - entry)
            rr = t1_reward / risk
            if rr < self.min_risk_reward:
                errors.append(f"T1 R:R too low: {rr:.2f} < {self.min_risk_reward}")

        # 4. Score threshold
        score = signal.get('score', signal.get('confidence_score', 0))
        if score < self.min_score:
            errors.append(f"Score too low: {score:.0f} < {self.min_score}")

        # 5. Volume confirmation check (if indicators available)
        if indicators:
            volume_ratio = indicators.get('volume_ratio', indicators.get('volume', 0) / indicators.get('volume_ma', 1))
            if volume_ratio < 1.2:
                errors.append(f"Insufficient volume confirmation: {volume_ratio:.2f}x")

        return {
            'valid': len(errors) == 0,
            'errors': errors
        }

    def validate_stop_loss(self, entry: float, sl: float, direction: str, ind: Dict) -> Tuple[bool, List[str]]:
        """
        Validate stop loss placement.

        Rules:
        - For LONG: SL < entry
        - For SHORT: SL > entry
        - Risk % between min_sl_pct and max_sl_pct
        """
        errors = []

        if entry <= 0 or sl <= 0:
            errors.append("Invalid entry or SL price (must be > 0)")
            return False, errors

        sl_pct = abs((sl - entry) / entry * 100)

        # Direction check
        if direction.upper() == 'LONG':
            if sl >= entry:
                errors.append("SL must be below entry for LONG signals")
        elif direction.upper() == 'SHORT':
            if sl <= entry:
                errors.append("SL must be above entry for SHORT signals")
        else:
            errors.append(f"Unknown direction: {direction}")

        # Not too tight
        if sl_pct < self.min_sl_pct:
            errors.append(f"SL too tight: {sl_pct:.2f}% < {self.min_sl_pct}%")

        # Not too wide
        if sl_pct > self.max_sl_pct:
            errors.append(f"SL too wide: {sl_pct:.2f}% > {self.max_sl_pct}%")

        return len(errors) == 0, errors

    def validate_targets(self, entry: float, sl: float, targets: List[float],
                        direction: str, ind: Dict) -> Tuple[bool, List[str]]:
        """
        Validate profit targets.

        Rules:
        - At least 2 targets required
        - Targets must be sequentially further from entry
        - Each target should have reasonable R:R
        """
        errors = []

        if not targets or len(targets) < self.min_targets:
            errors.append(f"Need at least {self.min_targets} targets")
            return False, errors

        risk = abs(entry - sl)
        if risk <= 0:
            errors.append("Invalid risk (entry and SL too close)")
            return False, errors

        prev_target = None
        for i, target in enumerate(targets, 1):
            if target <= 0:
                errors.append(f"T{i} invalid price (≤0)")
                continue

            reward = abs(target - entry)
            rr = reward / risk if risk > 0 else 0

            # R:R thresholds
            if i == 1 and rr < 1.5:
                errors.append(f"T1 R:R too low: {rr:.2f} < 1.5")
            if i == 2 and rr < 2.5:
                errors.append(f"T2 R:R too low: {rr:.2f} < 2.5")

            # Targets must progress in correct direction
            if direction.upper() == 'LONG':
                if target <= entry:
                    errors.append(f"T{i} must be > entry for LONG")
                if prev_target is not None and target <= prev_target:
                    errors.append(f"T{i} must be > T{i-1}")
            else:  # SHORT
                if target >= entry:
                    errors.append(f"T{i} must be < entry for SHORT")
                if prev_target is not None and target >= prev_target:
                    errors.append(f"T{i} must be < T{i-1}")

            prev_target = target

        # Check targets are not beyond reasonable resistance/support
        # (simple check: not beyond 2x risk from entry for T1)
        if len(targets) >= 1:
            t1 = targets[0]
            t1_distance = abs(t1 - entry) / entry * 100
            if t1_distance > 50:  # T1 is >50% away - suspicious
                errors.append(f"T1 too far from entry: {t1_distance:.1f}%")

        return len(errors) == 0, errors

    def validate_risk_reward(self, entry: float, sl: float, targets: List[float]) -> Dict:
        """
        Calculate R:R metrics for validation.

        Returns:
            Dict with risk, reward, rr ratios for each target
        """
        risk = abs(entry - sl)
        result = {'risk': risk, 'targets': []}

        for i, target in enumerate(targets, 1):
            reward = abs(target - entry)
            rr = reward / risk if risk > 0 else 0
            result['targets'].append({
                'target_num': i,
                'price': target,
                'reward': reward,
                'rr': round(rr, 2)
            })

        return result

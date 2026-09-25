"""FIFO cost-basis accounting for a sequence of unit-based transactions.

A purchase/SIP-installment/switch-in adds a "lot" (units bought at a
known cost per unit, on a known date). A redemption/switch-out consumes
the OLDEST lots first — First-In-First-Out — the convention real CAS
statements themselves state is used for redemption ordering (e.g. one
AMC's fine print: "Redemption of units would be done on First in First
out Basis (FIFO)"). This gives, purely from replaying the transaction
sequence:
- realized gain/loss on every unit actually sold (matched against the
  specific lot(s) it came from, with that lot's own holding period)
- the remaining open lots, i.e. what's still held, each at its own
  purchase-date cost per unit — the basis for weighted-average purchase
  NAV and unrealized gain

Pure and deterministic: no network access, no randomness (Rule 4 in the
project brief). Domain-agnostic — takes plain (date, units, amount)
triples, not any CAS-specific type, so it's reusable for any unit-based
holding, not just mutual funds parsed from a CAS.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

_ZERO_UNITS_TOLERANCE = 1e-9


@dataclass
class Lot:
    purchase_date: date
    units: float
    cost_per_unit: float

    @property
    def cost(self) -> float:
        return self.units * self.cost_per_unit


@dataclass
class RealizedLotConsumption:
    purchase_date: date
    redemption_date: date
    units: float
    cost_per_unit: float
    proceeds_per_unit: float

    @property
    def cost(self) -> float:
        return self.units * self.cost_per_unit

    @property
    def proceeds(self) -> float:
        return self.units * self.proceeds_per_unit

    @property
    def gain(self) -> float:
        return self.proceeds - self.cost

    @property
    def holding_period_days(self) -> int:
        return (self.redemption_date - self.purchase_date).days


@dataclass
class CostBasisResult:
    open_lots: list[Lot] = field(default_factory=list)
    consumptions: list[RealizedLotConsumption] = field(default_factory=list)
    # Units a redemption/switch-out event tried to consume beyond what any
    # open lot covered — should be ~0 for a correctly parsed, complete
    # transaction history; a non-zero value means the replayed ledger and
    # the statement's own running balance have diverged (e.g. a
    # transaction type not yet recognized by the caller), surfaced here
    # rather than silently fabricating a negative-units lot.
    unmatched_redemption_units: float = 0.0

    @property
    def remaining_units(self) -> float:
        return sum(lot.units for lot in self.open_lots)

    @property
    def remaining_cost(self) -> float:
        return sum(lot.cost for lot in self.open_lots)

    @property
    def weighted_average_purchase_nav(self) -> float | None:
        units = self.remaining_units
        return self.remaining_cost / units if units > _ZERO_UNITS_TOLERANCE else None

    @property
    def realized_gain(self) -> float:
        return sum(c.gain for c in self.consumptions)

    @property
    def realized_cost(self) -> float:
        return sum(c.cost for c in self.consumptions)

    @property
    def realized_proceeds(self) -> float:
        return sum(c.proceeds for c in self.consumptions)


def apply_fifo(events: list[tuple[date, float, float]]) -> CostBasisResult:
    """`events`: (date, units, amount) triples in the CAS's own sign
    convention — positive units/amount = units added to the holding
    (purchase/SIP/switch-in), negative = units removed
    (redemption/switch-out). Not required to be pre-sorted; replayed in
    date order (ties broken by the given order, matching how same-day
    transactions already appear in sequence within a CAS).
    """
    result = CostBasisResult()
    lots: list[Lot] = []

    for event_date, units, amount in sorted(events, key=lambda e: e[0]):
        if units > 0:
            cost_per_unit = amount / units
            lots.append(Lot(purchase_date=event_date, units=units, cost_per_unit=cost_per_unit))
            continue
        if units == 0:
            continue

        units_to_consume = -units
        proceeds_per_unit = (-amount) / units_to_consume
        while units_to_consume > _ZERO_UNITS_TOLERANCE and lots:
            lot = lots[0]
            consumed = min(lot.units, units_to_consume)
            result.consumptions.append(
                RealizedLotConsumption(
                    purchase_date=lot.purchase_date,
                    redemption_date=event_date,
                    units=consumed,
                    cost_per_unit=lot.cost_per_unit,
                    proceeds_per_unit=proceeds_per_unit,
                )
            )
            lot.units -= consumed
            units_to_consume -= consumed
            if lot.units <= _ZERO_UNITS_TOLERANCE:
                lots.pop(0)
        result.unmatched_redemption_units += units_to_consume

    result.open_lots = [lot for lot in lots if lot.units > _ZERO_UNITS_TOLERANCE]
    return result





# ST_TrueMomentum
# (c) 2026 Simpler Trading, LLC
# Last update 5/5/26
# Created by Sam Shames

declare lower;

plot _name = Double.NaN;
_name.SetDefaultColor(Color.WHITE);
_name.HideTitle();
_name.HideBubble();

# ─── Data Inputs ────────────────────────────────

def bn = BarNumber();
def preset = GetAggregationPeriod();
def higherTimeFrame;
def L1;
def L2;

if preset >= AggregationPeriod.QUARTER {
    higherTimeFrame = AggregationPeriod.QUARTER;
    L1 = 20;
    L2 = 30;
} else if preset >= AggregationPeriod.MONTH {
    higherTimeFrame = AggregationPeriod.QUARTER;
    L1 = 20;
    L2 = 23;
} else if preset >= AggregationPeriod.WEEK {
    higherTimeFrame = AggregationPeriod.MONTH;
    L1 = 15;
    L2 = 18;
} else if preset >= AggregationPeriod.THREE_DAYS {
    higherTimeFrame = AggregationPeriod.WEEK;
    L1 = 30;
    L2 = 100;
} else if preset >= AggregationPeriod.TWO_DAYS {
    higherTimeFrame = AggregationPeriod.WEEK;
    L1 = 30;
    L2 = 80;
} else if preset >= AggregationPeriod.DAY {
    higherTimeFrame = AggregationPeriod.WEEK;
    L1 = 21;
    L2 = 21;
} else if preset >= AggregationPeriod.FOUR_HOURS {
    higherTimeFrame = AggregationPeriod.THREE_DAYS;  
    L1 = 30;
    L2 = 35;
} else if preset >= AggregationPeriod.TWO_HOURS {
    higherTimeFrame = AggregationPeriod.THREE_DAYS;
    L1 = 30;
    L2 = 30;
} else if preset >= AggregationPeriod.HOUR {
    higherTimeFrame = AggregationPeriod.DAY;
    L1 = 30;
    L2 = 21;
} else if preset >= AggregationPeriod.THIRTY_MIN {
    higherTimeFrame = AggregationPeriod.FOUR_HOURS;
    L1 = 33;
    L2 = 40;
} else if preset >= AggregationPeriod.FIFTEEN_MIN {
    higherTimeFrame = AggregationPeriod.HOUR;
    L1 = 30;
    L2 = 30;
} else if preset >= AggregationPeriod.TEN_MIN {
    higherTimeFrame = AggregationPeriod.HOUR;
    L1 = 30;
    L2 = 30;
} else if preset >= AggregationPeriod.FIVE_MIN {
    higherTimeFrame = AggregationPeriod.THIRTY_MIN;
    L1 = 50;
    L2 = 50;
} else if preset >= AggregationPeriod.THREE_MIN {
    higherTimeFrame = AggregationPeriod.FIFTEEN_MIN;
    L1 = 50;
    L2 = 25;
} else if preset >= AggregationPeriod.TWO_MIN {
    higherTimeFrame = AggregationPeriod.TEN_MIN;
    L1 = 50;
    L2 = 30;
} else if preset >= AggregationPeriod.MIN {
    higherTimeFrame = AggregationPeriod.TEN_MIN;
    L1 = 50;
    L2 = 30;
} else {
    higherTimeFrame = AggregationPeriod.DAY;
    L1 = 50;
    L2 = 30;
}

def higherClose = close(period = higherTimeFrame);
def A1 = ExpAverage(higherClose - higherClose[1], L1);
def A2 = ExpAverage(AbsValue(higherClose - higherClose[1]), L1);
def A3 = if A2 > 0 then A1 / A2 else 0;

plot TrueMomentum = 50 * (A3 + 1);
TrueMomentum.SetLineWeight(5);
TrueMomentum.SetDefaultColor(CreateColor(0, 191, 0));

plot EMA = ExpAverage(TrueMomentum, L2);
EMA.SetLineWeight(5);
EMA.SetDefaultColor(Color.RED);

def crossUp = TrueMomentum crosses above EMA;
def crossDown = TrueMomentum crosses below EMA;
def strongBull = crossUp and (TrueMomentum - EMA) >= 9;
def strongBear = crossDown and (EMA - TrueMomentum) >= 9;
def confirmedBull = crossUp[1] and TrueMomentum > EMA;
def confirmedBear = crossDown[1] and TrueMomentum < EMA;
def finalBullSignal = strongBull or confirmedBull;
def finalBearSignal = strongBear or confirmedBear;

def startBar = Max(L1, L2) + 25;

def trendDirection = CompoundValue(1,
    if bn < startBar then 0
    else if finalBullSignal then 1
    else if finalBearSignal then -1
    else if trendDirection[1] != 0 then trendDirection[1]
    else if TrueMomentum > EMA then 1 else -1,
    0);

def newBullSignal = finalBullSignal and trendDirection[1] != 1 and bn >= startBar;
def newBearSignal = finalBearSignal and trendDirection[1] != -1 and bn >= startBar;

plot UpArrow = if newBullSignal then EMA else Double.NaN;
plot DownArrow = if newBearSignal then EMA else Double.NaN;

UpArrow.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
UpArrow.SetDefaultColor(Color.WHITE);
UpArrow.SetLineWeight(5);
UpArrow.HideBubble();
UpArrow.HideTitle();

DownArrow.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
DownArrow.SetDefaultColor(Color.WHITE);
DownArrow.SetLineWeight(5);
DownArrow.HideBubble();
DownArrow.HideTitle();

# ─── TrueMomentum + EMA Lines & Colors ──────────────────────────────────────────────────────────

TrueMomentum.AssignValueColor(if trendDirection == 1 or (trendDirection == 0 and TrueMomentum > EMA) then CreateColor(0, 191, 0) else Color.RED);
EMA.AssignValueColor(if trendDirection == 1 or (trendDirection == 0 and TrueMomentum > EMA) then CreateColor(0, 191, 0) else Color.RED);

# ─── Reference Lines ──────────────────────────────────────────────────────────

plot OverSold = 30;
plot OverBought = 70;
plot MidLine = 50;

OverSold.SetDefaultColor(Color.WHITE);
OverBought.SetDefaultColor(Color.WHITE);
MidLine.SetDefaultColor(Color.WHITE);
OverSold.SetLineWeight(5);
OverBought.SetLineWeight(5);
MidLine.SetLineWeight(5);
OverBought.HideBubble();
OverSold.HideBubble();
MidLine.HideBubble();
OverBought.HideTitle();
OverSold.HideTitle();
MidLine.HideTitle();

# ─── Momo Spreads ───────────────────────────────────────────────────────────

def OscHigh = TrueMomentum >= 69;
def EmaHigh = EMA >= 69;
def OscLow = TrueMomentum <= 31;
def EmaLow = EMA <= 31;
def BullDouble = OscHigh and EmaHigh and (TrueMomentum > EMA);
def BullEmaOnly = !OscHigh and EmaHigh;
def BullOscOnly = OscHigh and !EmaHigh;
def BearDouble = OscLow and EmaLow and (TrueMomentum < EMA);
def BearEmaOnly = !OscLow and EmaLow;
def BearOscOnly = OscLow and !EmaLow;

def PositiveSpreadOverride1 = TrueMomentum >= 65 and EMA >= 65 and (TrueMomentum - EMA) >= 0.1;
def NegativeSpreadOverride1 = TrueMomentum <= 35 and EMA <= 35 and (TrueMomentum - EMA) <= -0.1;

def PositiveSpreadOverride2 = TrueMomentum >= 60 and EMA >= 60 and (TrueMomentum - EMA) >= 0.8;
def NegativeSpreadOverride2 = TrueMomentum <= 40 and EMA <= 40 and (TrueMomentum - EMA) <= -0.8;

def BullTrend = TrueMomentum >= 55 and EMA >= 55 and (TrueMomentum - EMA) >= 3;
def BullTrend2 = TrueMomentum >= 51 and EMA >= 51 and (TrueMomentum - EMA) >= 3.5;

def BearTrend = TrueMomentum <= 50 and EMA <= 49.9 and (TrueMomentum - EMA) <= -1.5;
def BearTrend2 = TrueMomentum <= 45 and EMA <= 45 and (TrueMomentum - EMA) <= -1;

def BullishOverride = (TrueMomentum - EMA) >= 10;
def BearishOverride = (TrueMomentum - EMA) <= -10;

def TrendActive = PositiveSpreadOverride1 or PositiveSpreadOverride2 or NegativeSpreadOverride1 or NegativeSpreadOverride2 or BullishOverride or BearishOverride or BullTrend or BullTrend2 or BearTrend or BearTrend2 or BullDouble or BearDouble;

# ─── Caution Label ───────────────────────────────────────────────

AddLabel(BullEmaOnly or BearEmaOnly, "Caution", if BullEmaOnly then Color.RED else if BearEmaOnly then CreateColor(0, 191, 0) else Color.GRAY);

# ─── Momo Label ────────────────────────────────

AddLabel(yes, if TrendActive then
            if BullDouble or BearDouble then "Momo **"
            else if (BullOscOnly or BearOscOnly) or
                (BullishOverride and TrueMomentum >= 69) or
                (BearishOverride and TrueMomentum <= 31) then "Momo *"
            else if BullishOverride or BearishOverride then "Momo"
            else "Momo"
            else "Neutral",
            if PositiveSpreadOverride1 or PositiveSpreadOverride2 or BullishOverride or BullTrend or BullTrend2 or BullDouble
                 then CreateColor(0, 191, 0)
                else if NegativeSpreadOverride1 or NegativeSpreadOverride2 or BearishOverride or BearTrend or  
                 BearTrend2 or BearDouble then Color.RED                        
                    else Color.GRAY);

# ─── ATR Label ────────────────────────────────

def atrTrail = ATRTrailingStop("atr period" = 10, "atr factor" = 3.1, "average type" = "EXPONENTIAL", "trail type" = "modified");
def atrUp = close > atrTrail;
def atrDown = close < atrTrail;
AddLabel(yes, "ATR", if atrUp then CreateColor(0, 191, 0) else if atrDown then Color.RED else Color.GRAY);

# ─── Momentum Divergence ──────────────────────────────────────────────────────

def pivotStrength = 5;
def minBarsBetween = 10;
def maxBarsBetween = 100;
def oscDiffThreshold = 0.5;
def labelVisibleBars = 20;

def pivotLow  = Lowest(low[pivotStrength],  2 * pivotStrength + 1);
def pivotHigh = Highest(high[pivotStrength], 2 * pivotStrength + 1);
def isLow  = low[pivotStrength]  == pivotLow;
def isHigh = high[pivotStrength] == pivotHigh;
def lastLowBN = CompoundValue(1, if isLow then bn - pivotStrength else lastLowBN[1], 0);
def prevLowBN = CompoundValue(1, if isLow then lastLowBN[1] else prevLowBN[1], 0);
def lastLowPrice = CompoundValue(1, if isLow then low[pivotStrength] else lastLowPrice[1], low);
def prevLowPrice = CompoundValue(1, if isLow then lastLowPrice[1] else prevLowPrice[1], low);
def lastLowOsc = CompoundValue(1, if isLow then TrueMomentum[pivotStrength] else lastLowOsc[1], TrueMomentum);
def prevLowOsc = CompoundValue(1, if isLow then lastLowOsc[1] else prevLowOsc[1], TrueMomentum);
def lastHighBN = CompoundValue(1, if isHigh then bn - pivotStrength else lastHighBN[1], 0);
def prevHighBN = CompoundValue(1, if isHigh then lastHighBN[1] else prevHighBN[1], 0);
def lastHighPrice = CompoundValue(1, if isHigh then high[pivotStrength] else lastHighPrice[1], high);
def prevHighPrice = CompoundValue(1, if isHigh then lastHighPrice[1] else prevHighPrice[1], high);
def lastHighOsc = CompoundValue(1, if isHigh then TrueMomentum[pivotStrength] else lastHighOsc[1], TrueMomentum);
def prevHighOsc = CompoundValue(1, if isHigh then lastHighOsc[1] else prevHighOsc[1], TrueMomentum);
def barsBetweenLows  = if prevLowBN  > 0 and lastLowBN  > 0 then lastLowBN  - prevLowBN  else Double.NaN;
def barsBetweenHighs = if prevHighBN > 0 and lastHighBN > 0 then lastHighBN - prevHighBN else Double.NaN;

def bullDiv =
    prevLowBN > 0 and lastLowBN > 0 and
    barsBetweenLows >= minBarsBetween and barsBetweenLows <= maxBarsBetween and
    lastLowPrice < prevLowPrice and
    lastLowOsc > prevLowOsc and
    (lastLowOsc - prevLowOsc) >= oscDiffThreshold and
    bn == lastLowBN + pivotStrength;

def bearDiv =
    prevHighBN > 0 and lastHighBN > 0 and
    barsBetweenHighs >= minBarsBetween and barsBetweenHighs <= maxBarsBetween and
    lastHighPrice > prevHighPrice and
    lastHighOsc < prevHighOsc and
    (lastHighOsc - prevHighOsc) <= -oscDiffThreshold and
    bn == lastHighBN + pivotStrength;

def divRefLowPrice  = CompoundValue(1, if bullDiv then lastLowPrice  else divRefLowPrice[1],  Double.NaN);
def divRefLowOsc    = CompoundValue(1, if bullDiv then prevLowOsc    else divRefLowOsc[1],    Double.NaN);
def divRefHighPrice = CompoundValue(1, if bearDiv then lastHighPrice else divRefHighPrice[1], Double.NaN);
def divRefHighOsc   = CompoundValue(1, if bearDiv then prevHighOsc   else divRefHighOsc[1],   Double.NaN);

def divMachine = CompoundValue(1,
    if bullDiv then 100
    else if bearDiv then -100
    else if divMachine[1] > 0 then (
        if low < divRefLowPrice or TrueMomentum < divRefLowOsc then 0
        else if divMachine[1] - 100 + 1 >= labelVisibleBars then 0
        else divMachine[1] + 1)
    else if divMachine[1] < 0 then (
        if high > divRefHighPrice or TrueMomentum > divRefHighOsc then 0
        else if (-divMachine[1]) - 100 + 1 >= labelVisibleBars then 0
        else divMachine[1] - 1)
    else 0,
    0);

AddLabel(divMachine > 0, "Pos Div", Color.GRAY);
AddLabel(divMachine < 0, "Neg Div", Color.GRAY);

# ─── Trap Inputs ─────────────────────────────────────────────────────

def isDailyOrHigher = GetAggregationPeriod() >= AggregationPeriod.DAY;
def lookback = if isDailyOrHigher then 21 else 34;
def maxTrapAge = if isDailyOrHigher then 8 else 10;
def minConfirm = if isDailyOrHigher then 3 else 5;
def labelBars = if isDailyOrHigher then 5 else 8;
def bufferTicks = if isDailyOrHigher then 1 else 3;
def tickBuf = TickSize() * bufferTicks;

def swingHigh = Highest(high[1], lookback);
def swingLow = Lowest(low[1], lookback);
def newHigh = high > swingHigh[1] and high[1] <= swingHigh[1];
def newLow = low < swingLow[1] and low[1] >= swingLow[1];

# ─── Bull Trap ──────────────────────────────────────────────────────

def bullLevel = CompoundValue(1, if newHigh then high else bullLevel[1], Double.NaN);
def bullBN = CompoundValue(1, if newHigh then bn else bullBN[1], 0);
def bullAge = if newHigh then 0 else if bullBN > 0 then bn - bullBN else Double.NaN;
def bullInvalid = CompoundValue(1, if newHigh then 0 else if !IsNaN(bullLevel) and close > bullLevel + tickBuf then 1 else bullInvalid[1], 0);
def bullTrapTrigger = !IsNaN(bullLevel) and bullAge >= minConfirm and bullAge <= maxTrapAge and close < bullLevel and bullInvalid[1] == 0;

# ─── Bear Trap ──────────────────────────────────────────────────────

def bearLevel = CompoundValue(1, if newLow then low else bearLevel[1], Double.NaN);
def bearBN = CompoundValue(1, if newLow then bn else bearBN[1], 0);
def bearAge = if newLow then 0 else if bearBN > 0 then bn - bearBN else Double.NaN;
def bearInvalid = CompoundValue(1, if newLow then 0 else if !IsNaN(bearLevel) and close < bearLevel - tickBuf then 1 else bearInvalid[1], 0);
def bearTrapTrigger = !IsNaN(bearLevel) and bearAge >= minConfirm and bearAge <= maxTrapAge and close > bearLevel and bearInvalid[1] == 0;

def activeDir = CompoundValue(1,
    if bn == 1 then 0
    else if bullTrapTrigger then 1
    else if bearTrapTrigger then -1
    else activeDir[1],
    0);

def clearanceLevel = CompoundValue(1,
    if bullTrapTrigger then bullLevel
    else if bearTrapTrigger then bearLevel
    else if activeDir != activeDir[1] then Double.NaN
    else clearanceLevel[1],
    Double.NaN);

def trapStartBN = CompoundValue(1,
    if bullTrapTrigger or bearTrapTrigger then bn
    else if activeDir != activeDir[1] then Double.NaN
    else trapStartBN[1],
    Double.NaN);

def trapAge = if !IsNaN(trapStartBN) then bn - trapStartBN else Double.NaN;

def labelCountdown = CompoundValue(1,
    if bullTrapTrigger or bearTrapTrigger then labelBars
    else if labelCountdown[1] > 0 then labelCountdown[1] - 1
    else 0,
    0);

def cleared =
    (activeDir == 1  and !IsNaN(clearanceLevel) and close > clearanceLevel) or
    (activeDir == -1 and !IsNaN(clearanceLevel) and close < clearanceLevel);

def finalActive = CompoundValue(1,
    if activeDir == 0 or labelCountdown == 0 then 0
    else if cleared then 0
    else activeDir,
    0);

AddLabel(finalActive == 1 and labelCountdown > 0, "Bull Trap", Color.GRAY);
AddLabel(finalActive == -1 and labelCountdown > 0, "Bear Trap", Color.GRAY);

# ─── Extreme Label ─────────────────────────────────────────────────────────

def isBullExtreme = TrueMomentum > 69;
def isBearExtreme = TrueMomentum < 31;
def bothBullExtreme = isBullExtreme and EMA > 69;
def bothBearExtreme = isBearExtreme and EMA < 31;

AddLabel(bothBullExtreme, "Extreme", CreateColor(0, 115, 255));
AddLabel(bothBearExtreme, "Extreme", CreateColor(0, 115, 255));





# ST_TrueMomentumScore
# (c) 2026 SimplerTrading, LLC
# Last update 5/5/26
# Created by Sam Shames

declare upper;

################# TREND LOGIC

def EMA10 = ExpAverage(close,10);
def EMA20 = ExpAverage(close,20);
def SMA50 = Average(close,50);
def SMA200 = Average(close,200);
def hasEnoughBarsFor200 = !IsNaN(SMA200);

def bull1 = EMA10 > EMA20;
def bull2 = EMA10 > SMA50;
def bull3 = EMA20 > SMA50;
def bull4 = if hasEnoughBarsFor200 then SMA50 > SMA200 else 0;

def bullCount = 
                (if bull1 then 2 else 0) +
                (if bull2 then 3 else 0) +
                (if bull3 then 3 else 0) +
                (if bull4 then 2 else 0);

def bear1 = EMA20 > EMA10;
def bear2 = SMA50 > EMA10;
def bear3 = SMA50 > EMA20;
def bear4 = if hasEnoughBarsFor200 then SMA200 > SMA50 else 0;

def bearCount = 
                (if bear1 then 2 else 0) +
                (if bear2 then 3 else 0) +
                (if bear3 then 3 else 0) +
                (if bear4 then 2 else 0);

def Bull_MA = if !hasEnoughBarsFor200 then
                  (if bullCount >= 7 then 35
                   else if bullCount >= 5 then 25
                   else if bullCount >= 3 then 10
                   else if bullCount >= 1 then 0
                   else 0)
              else
                  (if bullCount == 10 then 35
                   else if bullCount >= 7 then 30
                   else if bullCount >= 5 then 20
                   else if bullCount >= 3 then 10
                   else if bullCount >= 1 then 5
                   else 0);

def Bear_MA = if !hasEnoughBarsFor200 then
                  (if bearCount >= 7 then -35
                   else if bearCount >= 5 then -25
                   else if bearCount >= 3 then -10
                   else if bearCount >= 1 then 0
                   else 0)
              else
                  (if bearCount == 10 then -35
                   else if bearCount >= 7 then -30
                   else if bearCount >= 5 then -20
                   else if bearCount >= 3 then -10
                   else if bearCount >= 1 then -5
                   else 0);


################# ATR LOGIC

def ATRStop = ATRTrailingStop("atr period" = 10, "atr factor" = 3.1, "average type" = AverageType.EXPONENTIAL);
def ATR_Value = if close > ATRStop then 5 else -5;

################# MACD LOGIC

def fastLength = 55;
def slowLength = 75;
def macdLength = 55;
def averageType = AverageType.EXPONENTIAL;
def MACDLine = MovingAverage(averageType, close, fastLength) - MovingAverage(averageType, close, slowLength);
def SignalLine = MovingAverage(averageType, MACDLine, macdLength);
def MACDHistogram = MACDLine - SignalLine;

################# TRUE MOMENTUM INPUTS

script TO_X {
input preset = aggregationPeriod.DAY;

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

################# TRUE MOMENTUM LOGIC

def A1 = MovingAverage(AverageType.EXPONENTIAL, close(period = higherTimeFrame) - close(period = higherTimeFrame)[1], L1);
def A2 = MovingAverage(AverageType.EXPONENTIAL, AbsValue(close(period = higherTimeFrame) - close(period = higherTimeFrame)[1]), L1);
def A3 = if A2 != 0 then A1 / A2 else 0;

def TrueMomentum = 50 * (A3 + 1);
def EMA = ExpAverage(TrueMomentum, L2);

def BullishOverride = (TrueMomentum - EMA) >= 10;
def BearishOverride = (TrueMomentum - EMA) <= -10;

def ExtremeBull = TrueMomentum >= 65 and EMA >= 65;
def ExtremeBear = TrueMomentum <= 35 and EMA <= 35;

def DeltaBull = TrueMomentum >= 60 and EMA >= 60;
def DeltaBear = TrueMomentum <= 40 and EMA <= 40;

def TO_EMA_Delta = AbsValue(TrueMomentum - EMA);

def TO_A = if TO_EMA_Delta >= 1.4 then (if TrueMomentum > EMA then 15 else -15)

           else if ExtremeBull and TrueMomentum > EMA and TO_EMA_Delta >= 0.1 then 15
           else if ExtremeBear and TrueMomentum < EMA and TO_EMA_Delta >= 0.1 then -15
           
           else if DeltaBull and TrueMomentum > EMA and TO_EMA_Delta >= 0.8 then 15
           else if DeltaBear and TrueMomentum < EMA and TO_EMA_Delta >= 0.8 then -15
          
           else 0;

def PosBias = if ExtremeBull and TO_EMA_Delta >= 0.1 and TrueMomentum > EMA then 20
              else if ExtremeBear and TO_EMA_Delta >= 0.1 and TrueMomentum < EMA then -20

              else if DeltaBull and TO_EMA_Delta >= 2.5 and TrueMomentum > EMA then 20
          else if DeltaBear and TO_EMA_Delta >= 2.5 and TrueMomentum < EMA then -20
    
              else if TrueMomentum >= 55 and EMA >= 55 and TO_EMA_Delta >= 3 and TrueMomentum > EMA then 20
              else if TrueMomentum >= 51 and EMA >= 51 and TO_EMA_Delta >= 3.5 and TrueMomentum > EMA then 20

              else if TrueMomentum <= 50 and EMA <= 49.9 and TO_EMA_Delta >= 1.4 and TrueMomentum < EMA then -20
              
              else if TrueMomentum >= 50 and EMA >= 50 and TO_EMA_Delta >= 3 and TrueMomentum > EMA then 10
              else if TrueMomentum <= 50 and EMA <= 49.9 and TO_EMA_Delta >= 1 and TrueMomentum < EMA then -10 
             
              else 0;

def OverrideBias = if BullishOverride then 10 else if BearishOverride then -10 else 0;
def TO_B = if OverrideBias != 0 and (PosBias == 0 or Sign(OverrideBias) != Sign(PosBias)) then OverrideBias else PosBias;

def TO_C = if TO_EMA_Delta >= 3.4 then if TrueMomentum >= 50.5 and EMA <= 50 then 10 else if TrueMomentum <= 49.5 and EMA >= 50 then -10 else 0 else 0;

plot CompositeScore = TO_A + TO_B + TO_C;

}

################# HILO INPUTS

script HLP_X {

input preset = aggregationPeriod.DAY;

def over_bought_XW = 80;
def over_sold_XW = 20;
def KPeriod_XW = 20;
def DPeriod_XW = 50;

def over_bought_XD = 80;
def over_sold_XD = 20;
def KPeriod_XD = 20;
def DPeriod_XD = 50;

def over_bought_XI = 80;
def over_sold_XI = 20;
def KPeriod_XI = 20;
def DPeriod_XI = 50;

def A1;
def A2;
def P1;
def P2;
def P3;
def OB1;
def OS1;
def OB2;
def OS2;
def OB3;
def OS3;
def OB4;
def OS4;
def OB5;
def OS5;
def OB6;
def OS6;
def OB7;
def OS7;
def OB8;
def OS8;
def OB9;
def OS9;
def OB10;
def OS10;
def OB11;
def OS11;
def OB12;
def OS12;
def OB13;
def OS13;
def OB14;
def OS14;
def OB15;
def OS15;

if preset > AggregationPeriod.DAY {
    A1 = 80;
    A2 = 20;
    P1 = 50;
    P2 = 3;
    P3 = 3;
    OB15 = 73.25;
    OB14 = 72.35;
    OB13 = 68.8;
    OB12 = 67.03;
    OB11 = 65.3;
    OB10 = 62.4;
    OB9 = 58.75;
    OB8 = 55.9;
    OB7 = 50.11;
    OB6 = 47.4;
    OB5 = 43.4;
    OB4 = 40;
    OB3 = 37.25;
    OB2 = 34.45;
    OB1 = 28.66;

    OS1 = 76.25;
    OS2 = 72.55;
    OS3 = 70.11;
    OS4 = 67.5;
    OS5 = 65.85;
    OS6 = 62.6;
    OS7 = 60.5;
    OS8 = 56.4;
    OS9 = 53;
    OS10 = 45.3;
    OS11 = 42.5;
    OS12 = 40;
    OS13 = 37.4;
    OS14 = 35.15;
    OS15 = 33.2;

} else if preset == AggregationPeriod.DAY {
    A1 = 80;
    A2 = 20;
    P1 = 99;
    P2 = 3;
    P3 = 3;
    OB15 = 73.6;
    OB14 = 71.9;
    OB13 = 68.24;
    OB12 = 65.75;
    OB11 = 62.67;
    OB10 = 59.7;
    OB9 = 55;
    OB8 = 52.5;
    OB7 = 49.2;
    OB6 = 43.9;  
    OB5 = 41.9;
    OB4 = 38.2;
    OB3 = 34.94;
    OB2 = 33;
    OB1 = 29.5;

    OS1 = 77.95;
    OS2 = 74;
    OS3 = 72.36;
    OS4 = 70; 
    OS5 = 67.07;
    OS6 = 66.22;
    OS7 = 65.5;
    OS8 = 64.5;
    OS9 = 63;
    OS10 = 60.3;
    OS11 = 57;
    OS12 = 51.67;
    OS13 = 44.25;
    OS14 = 41.95;
    OS15 = 40;

} else {
    A1 = 80;
    A2 = 20;
    P1 = 50;
    P2 = 3;
    P3 = 3;
    OB15 = 74.5;
    OB14 = 73;
    OB13 = 69.95;
    OB12 = 67.9;
    OB11 = 65.4;
    OB10 = 61;
    OB9 = 57.05;
    OB8 = 52.4;
    OB7 = 47.9;
    OB6 = 43.9;
    OB5 = 40;
    OB4 = 38;
    OB3 = 34.9;
    OB2 = 32;
    OB1 = 27.6;

    OS1 = 75.65;
    OS2 = 73.4;
    OS3 = 71.1;
    OS4 = 70;
    OS5 = 67.95;
    OS6 = 65.5;
    OS7 = 63.6;
    OS8 = 62.45;
    OS9 = 59.9;
    OS10 = 58.1;
    OS11 = 55.9;
    OS12 = 48.01;
    OS13 = 45;
    OS14 = 42;
    OS15 = 39.9;
 
}

################# OB/OS LEVELS

def SlowK = reference StochasticFull(A1, A2, P1, P2, high, low, close, P3, AverageType.EXPONENTIAL).FullK;
def SlowD = reference StochasticFull(A1, A2, P1, P2, high, low, close, P3, AverageType.EXPONENTIAL).FullD;

def OverBought = A1;
def OverSold = A2;

def OverBought1 = OB1;
def OverSold1 = OS1;
def upD1 = SlowD crosses above OverSold1;
def downD1 = SlowD crosses below OverBought1;

def OverBought2 = OB2;
def OverSold2 = OS2;
def upD2 = SlowD crosses above OverSold2;
def downD2 = SlowD crosses below OverBought2;

def OverBought3 = OB3;
def OverSold3 = OS3;
def upD3 = SlowD crosses above OverSold3;
def downD3 = SlowD crosses below OverBought3;

def OverBought4 = OB4;
def OverSold4 = OS4;
def upD4 = SlowD crosses above OverSold4;
def downD4 = SlowD crosses below OverBought4;

def OverBought5 = OB5;
def OverSold5 = OS5;
def upD5 = SlowD crosses above OverSold5;
def downD5 = SlowD crosses below OverBought5;

def OverBought6 = OB6;
def OverSold6 = OS6;
def upD6 = SlowD crosses above OverSold6;
def downD6 = SlowD crosses below OverBought6;

def OverBought7 = OB7;
def OverSold7 = OS7;
def upD7 = SlowD crosses above OverSold7;
def downD7 = SlowD crosses below OverBought7;

def OverBought8 = OB8;
def OverSold8 = OS8;
def upD8 = SlowD crosses above OverSold8;
def downD8 = SlowD crosses below OverBought8;

def OverBought9 = OB9;
def OverSold9 = OS9;
def upD9 = SlowD crosses above OverSold9;
def downD9 = SlowD crosses below OverBought9;

def OverBought10 = OB10;
def OverSold10 = OS10;
def upD10 = SlowD crosses above OverSold10;
def downD10 = SlowD crosses below OverBought10;

def OverBought11 = OB11;
def OverSold11 = OS11;
def upD11 = SlowD crosses above OverSold11;
def downD11 = SlowD crosses below OverBought11;

def OverBought12 = OB12;
def OverSold12 = OS12;
def upD12 = SlowD crosses above OverSold12;
def downD12 = SlowD crosses below OverBought12;

def OverBought13 = OB13;
def OverSold13 = OS13;
def upD13 = SlowD crosses above OverSold13;
def downD13 = SlowD crosses below OverBought13;

def OverBought14 = OB14;
def OverSold14 = OS14;
def upD14 = SlowD crosses above OverSold14;
def downD14 = SlowD crosses below OverBought14;

def OverBought15 = OB15;
def OverSold15 = OS15;
def upD15 = SlowD crosses above OverSold15;
def downD15 = SlowD crosses below OverBought15;

def priceH = high;
def priceL = low;
def priceC = close;
def averageType_X = AverageType.EXPONENTIAL;

def X1;
def X2;
def X3;
def X4;

if preset > AggregationPeriod.DAY {

    X1 = over_bought_XW;
    X2 = over_sold_XW;
    X3 = KPeriod_XW;
    X4 = DPeriod_XW;

} else if preset == AggregationPeriod.DAY {

    X1 = over_bought_XD;
    X2 = over_sold_XD;
    X3 = KPeriod_XD;
    X4 = DPeriod_XD;

} else {

    X1 = over_bought_XI;
    X2 = over_sold_XI;
    X3 = KPeriod_XI;
    X4 = DPeriod_XI;

}

def SlowK_X = reference StochasticFull(X1, X2, X3, X4, priceH, priceL, priceC, 3, AverageType.EXPONENTIAL).FullK;
def SlowD_X = reference StochasticFull(X1, X2, X3, X4, priceH, priceL, priceC, 3, AverageType.EXPONENTIAL).FullD;
def OverBought_X = X1;
def OverSold_X = X2;

################# THRUST ROC

def OBSell = SlowD >= 85.71 and SlowD <= 87.38 and SlowD-SlowD[1] <= -1.88;
def OBSell2 = SlowD >= 92.11 and SlowD <= 94.329 and SlowD-SlowD[1] <= -2.11; 
def OBSell3 = SlowD >= 80.6 and SlowD <= 100 and SlowD-SlowD[1] <= -2.73;
def OBSell4 = SlowD >= 87.39 and SlowD <= 91.08 and SlowD-SlowD[1] <= -2.11;

def OBBuy = SlowD >= 90.68 and SlowD <= 93.16 and SlowD-SlowD[1] >= 2.08;
def OBBuy2 = SlowD >= 87 and SlowD <= 96 and SlowD-SlowD[1] >= 2.5;
def OBBuy3 = SlowD >= 93.48 and SlowD <= 95.43 and SlowD-SlowD[1] >= 1.405;
def OBBuy4 = SlowD >= 81 and SlowD <= 100 and SlowD-SlowD[1] >= 3.14;

def OSSell = SlowD <= 24.6 and SlowD >= 12.75 and SlowD-SlowD[1] <= -3.3;
def OSSell2 = SlowD <= 76 and SlowD >= 1 and SlowD-SlowD[1] <= -4.6;
def OSSell3 = SlowD <= 100 and SlowD >= 1 and SlowD-SlowD[1] <= -6;

def OSBuy = SlowD <= 100 and SlowD >= 37.6 and SlowD-SlowD[1] >= 4;
def OSBuy2 = SlowD <= 100 and SlowD >= 20.5 and SlowD-SlowD[1] >= 5.05;

def DoubleBuy = SlowD >= SlowD[1] * 1.42 and SlowD >= 10; 
def DoubleBuy2 = SlowD >= SlowD[1] * 1.57 and SlowD >= 7.5 and SlowD < 10;
def DoubleSell = SlowD <= SlowD[1] * 0.86 and SlowD >= 10;

################# THRUST LOGIC

def anyBuy = upD1 or upD2 or upD3 or upD4 or upD5 or upD6 or upD7 or upD8 or upD9 or upD10 or upD11 or upD12 or upD13 or upD14 or upD15 or OBBuy or OBBuy2 or OBBuy3 or OBBuy4 or OSBuy or OSBuy2 or DoubleBuy or DoubleBuy2;

def anySell = downD1 or downD2 or downD3 or downD4 or downD5 or downD6 or downD7 or downD8 or downD9 or downD10 or downD11 or downD12 or downD13 or downD14 or downD15 or OSSell or OSSell2 or OSSell3 or OBSell or OBSell2 or OBSell3 or OBSell4 or DoubleSell;

def thrust = CompoundValue(1, if anyBuy then 1 else if anySell then -1 else thrust[1], 0);
def BullCycle = SlowD > SlowD_X;
def BearCycle = SlowD < SlowD_X;

def HLP_A = if thrust == 1 then 5 else if thrust == -1 then -5 else 0;
def HLP_B = if thrust == 1 and BullCycle then 15 else if thrust == -1 and BearCycle then -15 else 0;

plot HLP_Output = HLP_A + HLP_B;

}

################# TOTAL SCORE DEFS

def TrueMomentumScore = TO_X(GetAggregationPeriod());
def HiLoThrust   = HLP_X(GetAggregationPeriod());

def baseScore = TrueMomentumScore + HiLoThrust + Bull_MA + Bear_MA + ATR_Value + 
                (if MACDHistogram > 0 then 5 else if MACDHistogram < 0 then -5 else 0);

def isIntraday = GetAggregationPeriod() < AggregationPeriod.DAY;
def penaltyCondition = isIntraday and hasEnoughBarsFor200 and close < SMA200 and baseScore >= -95 and baseScore <= 100;
def totalScore = baseScore + (if penaltyCondition then -5 else 0);

################# TOTAL SCORE LABEL

AddLabel(yes,
    if totalScore >= 100 then "Max Bull: " + totalScore + "%"
    else if totalScore >= 75 then "Bull: " + totalScore + "%"
    else if totalScore >= 45 then "Neutral ▴ : " + totalScore + "%"
    else if totalScore >= -34 then "Neutral: " + totalScore + "%"
    else if totalScore <= -100 then "Max Bear: " + totalScore + "%"
    else if totalScore <= -75 then "Bear: " + totalScore + "%"
    else if totalScore <= -45 then "Neutral ▾ : " + totalScore + "%"
    else "Neutral: " + totalScore + "%",
    if totalScore >= 100 then CreateColor(8, 116, 4)
    else if totalScore >= 75 then CreateColor(0, 191, 0)
    else if totalScore >= 45 then CreateColor(0, 115, 255)
    else if totalScore <= -100 then CreateColor(170, 0, 0)
    else if totalScore <= -75 then Color.RED
    else if totalScore <= -45 then CreateColor(60, 60, 110)
    else Color.GRAY);

################# TREND LABEL

def TrueTrend = (Bull_MA + Bear_MA + ATR_Value) * 100 / 40;
def Trend = if penaltyCondition then TrueTrend - 5 else TrueTrend;

AddLabel(yes, "Trend",
         if Trend >= 100 then CreateColor(8, 116, 4)
         else if Trend >= 75 then CreateColor(0, 191, 0)
         else if Trend <= -100 then CreateColor(170, 0, 0)
         else if Trend <= -75 then Color.RED
         else if Trend >= 50 and Trend < 75 then CreateColor(0, 115, 255)
         else if Trend <= -50 and Trend > -75 then CreateColor(60, 60, 110)
         else Color.GRAY);

################# MOMO LABEL

def momo = (TrueMomentumScore + HiLoThrust + (if MACDHistogram > 0 then 5 else if MACDHistogram < 0 then -5 else 0)) * 100 / 60;

AddLabel(yes, "Momo",
    if momo >= 100 then CreateColor(8, 116, 4)
    else if momo <= -100 then CreateColor(170, 0, 0)
    else if momo <= -70 then Color.RED
    else if momo >= 70 then CreateColor(0, 191, 0)
    else if momo >= 25 and momo < 70 then CreateColor(0, 115, 255)
    else if momo <= -25 and momo > -70 then CreateColor(60, 60, 110)
    else Color.GRAY);

#################  CANDLE COLORS

DefineGlobalColor("MaxBull",   CreateColor(8, 116, 4));
DefineGlobalColor("Bull",      CreateColor(0, 191, 0));
DefineGlobalColor("NeutralUp", Color.GRAY);
DefineGlobalColor("Neutral",   Color.GRAY);
DefineGlobalColor("NeutralDn", Color.GRAY);
DefineGlobalColor("Bear",      Color.RED);
DefineGlobalColor("MaxBear",   CreateColor(170, 0, 0));

input ShowCandleColors = yes;

AssignPriceColor(
    if !ShowCandleColors then Color.CURRENT
    else if totalScore >= 95  then GlobalColor("MaxBull")
    else if totalScore >= 75  then GlobalColor("Bull")
    else if totalScore >= 45  then GlobalColor("NeutralUp")
    else if totalScore <= -95 then GlobalColor("MaxBear")
    else if totalScore <= -75 then GlobalColor("Bear")
    else if totalScore <= -45 then GlobalColor("NeutralDn")
    else GlobalColor("Neutral"));

################# PULLBACK BUY/SELL LOGIC

input ShowBubbles = yes;      
input ATRLength = 14;
input ATRMult10 = 0.33;
input ATRMult20 = 0.45;
input BubbleTextStyle = {default BuySell, Arrows, BS};
#input ShowLabels  = yes;        

def atrVal = ATR(length = ATRLength);
def near10_bull = AbsValue(low - EMA10) <= atrVal * ATRMult10;
def near20_bull = AbsValue(low - EMA20) <= atrVal * ATRMult20;
def near10_bear = AbsValue(high - EMA10) <= atrVal * ATRMult10;
def near20_bear = AbsValue(high - EMA20) <= atrVal * ATRMult20;

def MaxBullPullback = totalScore >= 95 and near10_bull;
def BullPullback    = totalScore >= 75 and totalScore < 100 and near20_bull;

def MaxBearRally    = totalScore <= -95 and near10_bear;
def BearRally       = totalScore <= -75 and totalScore > -100 and near20_bear;

def newMaxBullPB    = MaxBullPullback and !MaxBullPullback[1];
def newBullPB       = BullPullback    and !BullPullback[1];
def newMaxBearRally = MaxBearRally    and !MaxBearRally[1];
def newBearRally    = BearRally       and !BearRally[1];

################# REVERSAL BUY/SELL LOGIC

def FromMaxBullToWeak = totalScore[1] >= 95 and totalScore <= 65;
def FromBullToWeak    = totalScore[1] >= 75 and totalScore[1] < 95 and totalScore <= 55;

def FromMaxBearToWeak = totalScore[1] <= -95 and totalScore >= -65;
def FromBearToWeak    = totalScore[1] <= -75 and totalScore[1] > -95 and totalScore >= -55;

def NeutralUpToBull = totalScore[1] <= 45 and totalScore >= 75;
def NeutralDnToBear = totalScore[1] >= -35 and totalScore <= -80;

def OtherBubbleActive = newMaxBullPB or newBullPB or newMaxBearRally or newBearRally or FromMaxBearToWeak or FromBearToWeak or FromMaxBullToWeak or FromBullToWeak;

################# BUY/SELL BUBBLE LOGIC

AddChartBubble(ShowBubbles and newMaxBullPB, low,
    if BubbleTextStyle == BubbleTextStyle.BuySell then "Buy"
    else if BubbleTextStyle == BubbleTextStyle.Arrows then "^"
    else "B",
    GlobalColor("Bull"), no);

AddChartBubble(ShowBubbles and newBullPB, low,
    if BubbleTextStyle == BubbleTextStyle.BuySell then "Buy"
    else if BubbleTextStyle == BubbleTextStyle.Arrows then "^"
    else "B",
    GlobalColor("Bull"), no);

AddChartBubble(ShowBubbles and newMaxBearRally, high,
    if BubbleTextStyle == BubbleTextStyle.BuySell then "Sell"
    else if BubbleTextStyle == BubbleTextStyle.Arrows then "v"
    else "S",
    GlobalColor("Bear"), yes);

AddChartBubble(ShowBubbles and newBearRally, high,
    if BubbleTextStyle == BubbleTextStyle.BuySell then "Sell"
    else if BubbleTextStyle == BubbleTextStyle.Arrows then "v"
    else "S",
    GlobalColor("Bear"), yes);

AddChartBubble(ShowBubbles and FromMaxBearToWeak, low,
    if BubbleTextStyle == BubbleTextStyle.BuySell then "Buy"
    else if BubbleTextStyle == BubbleTextStyle.Arrows then "^"
    else "B",
    Color.WHITE, no);

AddChartBubble(ShowBubbles and FromBearToWeak, low,
    if BubbleTextStyle == BubbleTextStyle.BuySell then "Buy"     
    else if BubbleTextStyle == BubbleTextStyle.Arrows then "^" else "B",
    Color.WHITE, no);

AddChartBubble(ShowBubbles and FromMaxBullToWeak, high,
    if BubbleTextStyle == BubbleTextStyle.BuySell then "Sell"
    else if BubbleTextStyle == BubbleTextStyle.Arrows then "v"
    else "S",
    Color.WHITE, yes);

AddChartBubble(ShowBubbles and FromBullToWeak, high,
    if BubbleTextStyle == BubbleTextStyle.BuySell then "Sell"
    else if BubbleTextStyle == BubbleTextStyle.Arrows then "v"
    else "S",
    Color.WHITE, yes);

AddChartBubble(ShowBubbles and NeutralUpToBull and !OtherBubbleActive, low,
    if BubbleTextStyle == BubbleTextStyle.BuySell then "Buy"
    else if BubbleTextStyle == BubbleTextStyle.Arrows then "^"
    else "B",
    GlobalColor("Bull"), no);

AddChartBubble(ShowBubbles and NeutralDnToBear and !OtherBubbleActive, high,
    if BubbleTextStyle == BubbleTextStyle.BuySell then "Sell"
    else if BubbleTextStyle == BubbleTextStyle.Arrows then "v"
    else "S",
    GlobalColor("Bear"), yes);

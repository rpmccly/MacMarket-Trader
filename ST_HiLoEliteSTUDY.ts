



# ST_HiLoElite
# (c) 2026 SimplerTrading, LLC
# Last update 5/5/26
# Created by Sam Shames

declare lower;

plot _name = Double.NaN;
_name.SetDefaultColor(Color.WHITE);
_name.HideTitle();
_name.HideBubble();

def preset = GetAggregationPeriod();

DefineGlobalColor("Bull", CreateColor(0, 191, 0));
DefineGlobalColor("Bear", Color.RED);
DefineGlobalColor("Neutral", Color.BLACK);
DefineGlobalColor("Bull2", CreateColor(0, 115, 255));
DefineGlobalColor("Bear2", CreateColor(0, 115, 255));

################# Levels Def

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

################# HiLo Defs

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

plot SlowK = reference StochasticFull(A1, A2, P1, P2, high, low, close, P3, AverageType.EXPONENTIAL).FullK;
plot SlowD = reference StochasticFull(A1, A2, P1, P2, high, low, close, P3, AverageType.EXPONENTIAL).FullD;
plot OverBought = A1;
plot OverSold = A2;
OverBought.SetDefaultColor(Color.WHITE);
OverSold.SetDefaultColor(Color.WHITE);
OverBought.SetLineWeight(5);
OverSold.SetLineWeight(5);
OverBought.HideBubble();
OverSold.HideBubble();
OverBought.HideTitle();
OverSold.HideTitle();

################# Crossover Defs

def upD1 = SlowD crosses above OS1;
def downD1 = SlowD crosses below OB1;
def upD2 = SlowD crosses above OS2;
def downD2 = SlowD crosses below OB2;
def upD3 = SlowD crosses above OS3;
def downD3 = SlowD crosses below OB3;
def upD4 = SlowD crosses above OS4;
def downD4 = SlowD crosses below OB4;
def upD5 = SlowD crosses above OS5;
def downD5 = SlowD crosses below OB5;
def upD6 = SlowD crosses above OS6;
def downD6 = SlowD crosses below OB6;
def upD7 = SlowD crosses above OS7;
def downD7 = SlowD crosses below OB7;
def upD8 = SlowD crosses above OS8;
def downD8 = SlowD crosses below OB8;
def upD9 = SlowD crosses above OS9;
def downD9 = SlowD crosses below OB9;
def upD10 = SlowD crosses above OS10;
def downD10 = SlowD crosses below OB10;
def upD11 = SlowD crosses above OS11;
def downD11 = SlowD crosses below OB11;
def upD12 = SlowD crosses above OS12;
def downD12 = SlowD crosses below OB12;
def upD13 = SlowD crosses above OS13;
def downD13 = SlowD crosses below OB13;
def upD14 = SlowD crosses above OS14;
def downD14 = SlowD crosses below OB14;
def upD15 = SlowD crosses above OS15;
def downD15 = SlowD crosses below OB15;

################# OB/OS Levels + RoC

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

################# Up/Down Defs

def anyBuy = upD1 or upD2 or upD3 or upD4 or upD5 or upD6 or upD7 or upD8 or upD9 or upD10 or upD11 or upD12 or upD13 or upD14 or upD15 or OBBuy or OBBuy2 or OBBuy3 or OBBuy4 or OSBuy or OSBuy2 or DoubleBuy or DoubleBuy2;
def anySell = downD1 or downD2 or downD3 or downD4 or downD5 or downD6 or downD7 or downD8 or downD9 or downD10 or downD11 or downD12 or downD13 or downD14 or downD15 or OSSell or OSSell2 or OSSell3 or OBSell or OBSell2 or OBSell3 or OBSell4 or DoubleSell;

################# Line Colors

def thrust = CompoundValue(1, if anyBuy then 1 else if anySell then -1 else thrust[1], 0);
SlowD.AssignValueColor(if thrust == 1 then CreateColor(0, 191, 0)
             else if thrust == -1 then Color.RED else Color.GRAY);
SlowD.SetLineWeight(5);

################# Thrust Helpers

def isNewBuyThrust  = thrust[1] != 1;
def isNewSellThrust = thrust[1] != -1;

################# Arrows

def buyArrowLevel =
    if upD1  and isNewBuyThrust then OS1
    else if upD2  and isNewBuyThrust then OS2
    else if upD3  and isNewBuyThrust then OS3
    else if upD4  and isNewBuyThrust then OS4
    else if upD5  and isNewBuyThrust then OS5
    else if upD6  and isNewBuyThrust then OS6
    else if upD7  and isNewBuyThrust then OS7
    else if upD8  and isNewBuyThrust then OS8
    else if upD9  and isNewBuyThrust then OS9
    else if upD10 and isNewBuyThrust then OS10
    else if upD11 and isNewBuyThrust then OS11
    else if upD12 and isNewBuyThrust then OS12
    else if upD13 and isNewBuyThrust then OS13
    else if upD14 and isNewBuyThrust then OS14
    else if upD15 and isNewBuyThrust then OS15
    else if OBBuy  and isNewBuyThrust then SlowD
    else if OBBuy2 and isNewBuyThrust then SlowD
    else if OBBuy3 and isNewBuyThrust then SlowD
    else if OBBuy4 and isNewBuyThrust then SlowD
    else if OSBuy  and isNewBuyThrust then SlowD
    else if OSBuy2 and isNewBuyThrust then SlowD
    else if DoubleBuy  and isNewBuyThrust then SlowD
    else if DoubleBuy2 and isNewBuyThrust then SlowD
    else Double.NaN;

def sellArrowLevel =
    if downD1  and isNewSellThrust then OB1
    else if downD2  and isNewSellThrust then OB2
    else if downD3  and isNewSellThrust then OB3
    else if downD4  and isNewSellThrust then OB4
    else if downD5  and isNewSellThrust then OB5
    else if downD6  and isNewSellThrust then OB6
    else if downD7  and isNewSellThrust then OB7
    else if downD8  and isNewSellThrust then OB8
    else if downD9  and isNewSellThrust then OB9
    else if downD10 and isNewSellThrust then OB10
    else if downD11 and isNewSellThrust then OB11
    else if downD12 and isNewSellThrust then OB12
    else if downD13 and isNewSellThrust then OB13
    else if downD14 and isNewSellThrust then OB14
    else if downD15 and isNewSellThrust then OB15
    else if OBSell  and isNewSellThrust then SlowD
    else if OBSell2 and isNewSellThrust then SlowD
    else if OBSell3 and isNewSellThrust then SlowD
    else if OBSell4 and isNewSellThrust then SlowD
    else if OSSell  and isNewSellThrust then SlowD
    else if OSSell2 and isNewSellThrust then SlowD
    else if OSSell3 and isNewSellThrust then SlowD
    else if DoubleSell and isNewSellThrust then SlowD
    else Double.NaN;

plot BuyArrow = buyArrowLevel;
BuyArrow.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
BuyArrow.SetDefaultColor(Color.WHITE);
BuyArrow.SetLineWeight(5);
BuyArrow.HideBubble();
BuyArrow.HideTitle();

plot SellArrow = sellArrowLevel;
SellArrow.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
SellArrow.SetDefaultColor(Color.WHITE);
SellArrow.SetLineWeight(5);
SellArrow.HideBubble();
SellArrow.HideTitle();

################# OB/OS Defs

plot OverBought1 = OB1;
plot OverSold1 = OS1;
plot UpSignal1 = Double.NaN;
plot DownSignal1 = Double.NaN;
SlowK.SetDefaultColor(GetColor(5));
SlowK.Hide();
OverBought1.SetDefaultColor(Color.WHITE);
OverSold1.SetDefaultColor(Color.WHITE);
OverBought1.SetLineWeight(3);
OverSold1.SetLineWeight(3);
OverBought1.Hide();
OverSold1.Hide();
UpSignal1.SetDefaultColor(Color.WHITE);
UpSignal1.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
DownSignal1.SetDefaultColor(Color.WHITE);
DownSignal1.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
UpSignal1.SetLineWeight(5);
DownSignal1.SetLineWeight(5);
UpSignal1.HideTitle();
DownSignal1.HideTitle();
UpSignal1.HideBubble();
DownSignal1.HideBubble();

plot OverBought2 = OB2;
plot OverSold2 = OS2;
plot UpSignal2 = Double.NaN;
plot DownSignal2 = Double.NaN;
OverBought2.SetDefaultColor(Color.WHITE);
OverSold2.SetDefaultColor(Color.WHITE);
OverBought2.SetLineWeight(5);
OverSold2.SetLineWeight(5);
OverBought2.Hide();
OverSold2.Hide();
UpSignal2.SetDefaultColor(Color.WHITE);
UpSignal2.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
DownSignal2.SetDefaultColor(Color.WHITE);
DownSignal2.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
UpSignal2.SetLineWeight(5);
DownSignal2.SetLineWeight(5);
UpSignal2.HideTitle();
DownSignal2.HideTitle();
UpSignal2.HideBubble();
DownSignal2.HideBubble();

plot OverBought3 = OB3;
plot OverSold3 = OS3;
plot UpSignal3 = Double.NaN;
plot DownSignal3 = Double.NaN;
OverBought3.SetDefaultColor(Color.WHITE);
OverSold3.SetDefaultColor(Color.WHITE);
OverBought3.SetLineWeight(3);
OverSold3.SetLineWeight(3);
OverBought3.Hide();
OverSold3.Hide();
UpSignal3.SetDefaultColor(Color.WHITE);
UpSignal3.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
DownSignal3.SetDefaultColor(Color.WHITE);
DownSignal3.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
UpSignal3.SetLineWeight(5);
DownSignal3.SetLineWeight(5);
UpSignal3.HideTitle();
DownSignal3.HideTitle();
UpSignal3.HideBubble();
DownSignal3.HideBubble();

plot UpSignal4 = Double.NaN;
plot DownSignal4 = Double.NaN;
UpSignal4.SetDefaultColor(Color.WHITE);
UpSignal4.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
DownSignal4.SetDefaultColor(Color.WHITE);
DownSignal4.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
UpSignal4.SetLineWeight(5);
DownSignal4.SetLineWeight(5);
UpSignal4.HideTitle();
DownSignal4.HideTitle();
UpSignal4.HideBubble();
DownSignal4.HideBubble();

plot UpSignal5 = Double.NaN;
plot DownSignal5 = Double.NaN;
UpSignal5.SetDefaultColor(Color.WHITE);
UpSignal5.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
DownSignal5.SetDefaultColor(Color.WHITE);
DownSignal5.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
UpSignal5.SetLineWeight(5);
DownSignal5.SetLineWeight(5);
UpSignal5.HideTitle();
DownSignal5.HideTitle();
UpSignal5.HideBubble();
DownSignal5.HideBubble();

plot UpSignal6 = Double.NaN;
plot DownSignal6 = Double.NaN;
UpSignal6.SetDefaultColor(Color.WHITE);
UpSignal6.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
DownSignal6.SetDefaultColor(Color.WHITE);
DownSignal6.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
UpSignal6.SetLineWeight(5);
DownSignal6.SetLineWeight(5);
UpSignal6.HideTitle();
DownSignal6.HideTitle();
UpSignal6.HideBubble();
DownSignal6.HideBubble();

plot UpSignal7 = Double.NaN;
plot DownSignal7 = Double.NaN;
UpSignal7.SetDefaultColor(Color.WHITE);
UpSignal7.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
DownSignal7.SetDefaultColor(Color.WHITE);
DownSignal7.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
UpSignal7.SetLineWeight(5);
DownSignal7.SetLineWeight(5);
UpSignal7.HideTitle();
DownSignal7.HideTitle();
UpSignal7.HideBubble();
DownSignal7.HideBubble();

plot UpSignal8 = Double.NaN;
plot DownSignal8 = Double.NaN;
UpSignal8.SetDefaultColor(Color.WHITE);
UpSignal8.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
DownSignal8.SetDefaultColor(Color.WHITE);
DownSignal8.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
UpSignal8.SetLineWeight(5);
DownSignal8.SetLineWeight(5);
UpSignal8.HideTitle();
DownSignal8.HideTitle();
UpSignal8.HideBubble();
DownSignal8.HideBubble();

plot UpSignal9 = Double.NaN;
plot DownSignal9 = Double.NaN;
UpSignal9.SetDefaultColor(Color.WHITE);
UpSignal9.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
DownSignal9.SetDefaultColor(Color.WHITE);
DownSignal9.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
UpSignal9.SetLineWeight(5);
DownSignal9.SetLineWeight(5);
UpSignal9.HideTitle();
DownSignal9.HideTitle();
UpSignal9.HideBubble();
DownSignal9.HideBubble();

plot UpSignal10 = Double.NaN;
plot DownSignal10 = Double.NaN;
UpSignal10.SetDefaultColor(Color.WHITE);
UpSignal10.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
DownSignal10.SetDefaultColor(Color.WHITE);
DownSignal10.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
UpSignal10.SetLineWeight(5);
DownSignal10.SetLineWeight(5);
UpSignal10.HideTitle();
DownSignal10.HideTitle();
UpSignal10.HideBubble();
DownSignal10.HideBubble();

plot UpSignal11 = Double.NaN;
plot DownSignal11 = Double.NaN;
UpSignal11.SetDefaultColor(Color.WHITE);
UpSignal11.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
DownSignal11.SetDefaultColor(Color.WHITE);
DownSignal11.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
UpSignal11.SetLineWeight(5);
DownSignal11.SetLineWeight(5);
UpSignal11.HideTitle();
DownSignal11.HideTitle();
UpSignal11.HideBubble();
DownSignal11.HideBubble();

plot UpSignal12 = Double.NaN;
plot DownSignal12 = Double.NaN;
UpSignal12.SetDefaultColor(Color.WHITE);
UpSignal12.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
DownSignal12.SetDefaultColor(Color.WHITE);
DownSignal12.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
UpSignal12.SetLineWeight(5);
DownSignal12.SetLineWeight(5);
UpSignal12.HideTitle();
DownSignal12.HideTitle();
UpSignal12.HideBubble();
DownSignal12.HideBubble();

plot UpSignal13 = Double.NaN;
plot DownSignal13 = Double.NaN;
UpSignal13.SetDefaultColor(Color.WHITE);
UpSignal13.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
DownSignal13.SetDefaultColor(Color.WHITE);
DownSignal13.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
UpSignal13.SetLineWeight(5);
DownSignal13.SetLineWeight(5);
UpSignal13.HideTitle();
DownSignal13.HideTitle();
UpSignal13.HideBubble();
DownSignal13.HideBubble();

plot UpSignal14 = Double.NaN;
plot DownSignal14 = Double.NaN;
UpSignal14.SetDefaultColor(Color.WHITE);
UpSignal14.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
DownSignal14.SetDefaultColor(Color.WHITE);
DownSignal14.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
UpSignal14.SetLineWeight(5);
DownSignal14.SetLineWeight(5);
UpSignal14.HideTitle();
DownSignal14.HideTitle();
UpSignal14.HideBubble();
DownSignal14.HideBubble();

plot UpSignal15 = Double.NaN;
plot DownSignal15 = Double.NaN;
UpSignal15.SetDefaultColor(Color.WHITE);
UpSignal15.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
DownSignal15.SetDefaultColor(Color.WHITE);
DownSignal15.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
UpSignal15.SetLineWeight(5);
DownSignal15.SetLineWeight(5);
UpSignal15.HideTitle();
DownSignal15.HideTitle();
UpSignal15.HideBubble();
DownSignal15.HideBubble();

plot fifty = 50;
fifty.SetDefaultColor(Color.WHITE);
fifty.SetLineWeight(5);
fifty.HideBubble();
fifty.HideTitle();

##################################### Data Defs & Plots

def X1 = if preset > AggregationPeriod.DAY then over_bought_XW else if preset == AggregationPeriod.DAY then over_bought_XD else over_bought_XI;
def X2 = if preset > AggregationPeriod.DAY then over_sold_XW else if preset == AggregationPeriod.DAY then over_sold_XD else over_sold_XI;
def X3 = if preset > AggregationPeriod.DAY then KPeriod_XW else if preset == AggregationPeriod.DAY then KPeriod_XD else KPeriod_XI;
def X4 = if preset > AggregationPeriod.DAY then DPeriod_XW else if preset == AggregationPeriod.DAY then DPeriod_XD else DPeriod_XI;

plot SlowK_X = reference StochasticFull(X1, X2, X3, X4, high, low, close, 3, AverageType.EXPONENTIAL).FullK;
plot SlowD_X = reference StochasticFull(X1, X2, X3, X4, high, low, close, 3, AverageType.EXPONENTIAL).FullD;
plot OverBought_X = X1;
plot OverSold_X = X2;

SlowK_X.SetDefaultColor(GetColor(5));
SlowD_X.AssignValueColor(if SlowD > SlowD_X then CreateColor(0, 191, 0) else Color.RED);
SlowK_X.SetLineWeight(5);
SlowD_X.SetLineWeight(5);

SlowK_X.Hide();
SlowD_X.Hide();
OverBought_X.SetDefaultColor(GetColor(1));
OverSold_X.SetDefaultColor(GetColor(1));
OverBought_X.Hide();
OverSold_X.Hide();
OverBought_X.HideTitle();
OverSold_X.HideTitle();
SlowD_X.HideBubble();
SlowD_X.HideTitle();

################# Double Thrust Signal

def buyCount = (if upD1   and isNewBuyThrust then 1 else 0) +
               (if upD2   and isNewBuyThrust then 1 else 0) +
               (if upD3   and isNewBuyThrust then 1 else 0) +
               (if upD4   and isNewBuyThrust then 1 else 0) +
               (if upD5   and isNewBuyThrust then 1 else 0) +
               (if upD6   and isNewBuyThrust then 1 else 0) +
               (if upD7   and isNewBuyThrust then 1 else 0) +
               (if upD8   and isNewBuyThrust then 1 else 0) +
               (if upD9   and isNewBuyThrust then 1 else 0) +
               (if upD10  and isNewBuyThrust then 1 else 0) +
               (if upD11  and isNewBuyThrust then 1 else 0) +
               (if upD12  and isNewBuyThrust then 1 else 0) +
               (if upD13  and isNewBuyThrust then 1 else 0) +
               (if upD14  and isNewBuyThrust then 1 else 0) +
               (if upD15  and isNewBuyThrust then 1 else 0) +
               (if OBBuy  and isNewBuyThrust then 1 else 0) +
               (if OBBuy2 and isNewBuyThrust then 1 else 0) +
               (if OBBuy3 and isNewBuyThrust then 1 else 0) +
               (if OBBuy4 and isNewBuyThrust then 1 else 0) +
               (if OSBuy  and isNewBuyThrust then 1 else 0) +
               (if OSBuy2 and isNewBuyThrust then 1 else 0) +
               (if DoubleBuy and isNewBuyThrust then 1 else 0) +
               (if DoubleBuy2 and isNewBuyThrust then 1 else 0);

def sellCount = (if downD1   and isNewSellThrust then 1 else 0) +
                (if downD2   and isNewSellThrust then 1 else 0) +
                (if downD3   and isNewSellThrust then 1 else 0) +
                (if downD4   and isNewSellThrust then 1 else 0) +
                (if downD5   and isNewSellThrust then 1 else 0) +
                (if downD6   and isNewSellThrust then 1 else 0) +
                (if downD7   and isNewSellThrust then 1 else 0) +
                (if downD8   and isNewSellThrust then 1 else 0) +
                (if downD9   and isNewSellThrust then 1 else 0) +
                (if downD10  and isNewSellThrust then 1 else 0) +
                (if downD11  and isNewSellThrust then 1 else 0) +
                (if downD12  and isNewSellThrust then 1 else 0) +
                (if downD13  and isNewSellThrust then 1 else 0) +
                (if downD14  and isNewSellThrust then 1 else 0) +
                (if downD15  and isNewSellThrust then 1 else 0) +
                (if OBSell   and isNewSellThrust then 1 else 0) +
                (if OBSell2  and isNewSellThrust then 1 else 0) +
                (if OBSell3  and isNewSellThrust then 1 else 0) +
                (if OBSell4  and isNewSellThrust then 1 else 0) +
                (if OSSell   and isNewSellThrust then 1 else 0) +
                (if OSSell2  and isNewSellThrust then 1 else 0) +
                (if OSSell3  and isNewSellThrust then 1 else 0) +
                (if DoubleSell and isNewSellThrust then 1 else 0);

def upArrowsThisBar = buyCount;
def downArrowsThisBar = sellCount;

def strongUpTrigger = upArrowsThisBar >= 2;
def strongDownTrigger = downArrowsThisBar >= 2;
def strongDirection = CompoundValue(1,
    if strongUpTrigger then 1
    else if strongDownTrigger then -1
    else if strongDirection[1] == 1 and downArrowsThisBar >= 1 then 0
    else if strongDirection[1] == -1 and upArrowsThisBar >= 1 then 0
    else strongDirection[1], 0);
def isStrong = strongDirection != 0;

################# OB and OS Levels

plot OverBoughtSell = Double.NaN;
OverBoughtSell.SetDefaultColor(Color.WHITE);
OverBoughtSell.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
OverBoughtSell.SetLineWeight(5);
OverBoughtSell.HideBubble();
OverBoughtSell.HideTitle();

plot OverBoughtSell2 = Double.NaN;
OverBoughtSell2.SetDefaultColor(Color.WHITE);
OverBoughtSell2.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
OverBoughtSell2.SetLineWeight(5);
OverBoughtSell2.HideBubble();
OverBoughtSell2.HideTitle();

plot OverBoughtSell3 = Double.NaN;
OverBoughtSell3.SetDefaultColor(Color.WHITE);
OverBoughtSell3.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
OverBoughtSell3.SetLineWeight(5);
OverBoughtSell3.HideBubble();
OverBoughtSell3.HideTitle();

plot OverBoughtSell4 = Double.NaN;
OverBoughtSell4.SetDefaultColor(Color.WHITE);
OverBoughtSell4.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
OverBoughtSell4.SetLineWeight(5);
OverBoughtSell4.HideBubble();
OverBoughtSell4.HideTitle();

plot OverBoughtBuy = Double.NaN;
OverBoughtBuy.SetDefaultColor(Color.WHITE);
OverBoughtBuy.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
OverBoughtBuy.SetLineWeight(5);
OverBoughtBuy.HideBubble();
OverBoughtBuy.HideTitle();

plot OverBoughtBuy2 = Double.NaN;
OverBoughtBuy2.SetDefaultColor(Color.WHITE);
OverBoughtBuy2.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
OverBoughtBuy2.SetLineWeight(5);
OverBoughtBuy2.HideBubble();
OverBoughtBuy2.HideTitle();

plot OverBoughtBuy3 = Double.NaN;
OverBoughtBuy3.SetDefaultColor(Color.WHITE);
OverBoughtBuy3.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
OverBoughtBuy3.SetLineWeight(5);
OverBoughtBuy3.HideBubble();
OverBoughtBuy3.HideTitle();

plot OverBoughtBuy4 = Double.NaN;
OverBoughtBuy4.SetDefaultColor(Color.WHITE);
OverBoughtBuy4.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
OverBoughtBuy4.SetLineWeight(5);
OverBoughtBuy4.HideBubble();
OverBoughtBuy4.HideTitle();

plot OverSoldSell = Double.NaN;
OverSoldSell.SetDefaultColor(Color.WHITE);
OverSoldSell.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
OverSoldSell.SetLineWeight(5);
OverSoldSell.HideBubble();
OverSoldSell.HideTitle();

plot OverSoldSell2 = Double.NaN;
OverSoldSell2.SetDefaultColor(Color.WHITE);
OverSoldSell2.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
OverSoldSell2.SetLineWeight(5);
OverSoldSell2.HideBubble();
OverSoldSell2.HideTitle();

plot OverSoldBuy = Double.NaN;
OverSoldBuy.SetDefaultColor(Color.WHITE);
OverSoldBuy.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
OverSoldBuy.SetLineWeight(5);
OverSoldBuy.HideBubble();
OverSoldBuy.HideTitle();

plot OverSoldBuy2 = Double.NaN;
OverSoldBuy2.SetDefaultColor(Color.WHITE);
OverSoldBuy2.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
OverSoldBuy2.SetLineWeight(5);
OverSoldBuy2.HideBubble();
OverSoldBuy2.HideTitle();

plot UpSignalDouble = Double.NaN;
UpSignalDouble.SetDefaultColor(Color.WHITE);
UpSignalDouble.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
UpSignalDouble.SetLineWeight(5);
UpSignalDouble.HideBubble();
UpSignalDouble.HideTitle();

plot UpSignalDouble2 = Double.NaN;
UpSignalDouble2.SetDefaultColor(Color.WHITE);
UpSignalDouble2.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
UpSignalDouble2.SetLineWeight(5);
UpSignalDouble2.HideBubble();
UpSignalDouble2.HideTitle();

plot DownSignalDouble = Double.NaN;
DownSignalDouble.SetDefaultColor(Color.WHITE);
DownSignalDouble.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
DownSignalDouble.SetLineWeight(5);
DownSignalDouble.HideBubble();
DownSignalDouble.HideTitle();

################# Slingshot & Strong Labels

def lastBuyBar = CompoundValue(1, if anyBuy then BarNumber() else lastBuyBar[1], 0);
def lastSellBar = CompoundValue(1, if anySell then BarNumber() else lastSellBar[1], 0);
def validZone = (SlowD <= 40) or (SlowD >= 60);
def bullSlingshotEvent = anyBuy and (BarNumber() - lastSellBar <= 2) and validZone;
def bearSlingshotEvent = anySell and (BarNumber() - lastBuyBar <= 2) and validZone;
def bullSlingshotSticky = CompoundValue(1, if bullSlingshotEvent then 1 else if anySell then 0 else bullSlingshotSticky[1], 0);
def bearSlingshotSticky = CompoundValue(1, if bearSlingshotEvent then 1 else if anyBuy then 0 else bearSlingshotSticky[1], 0);

AddLabel(yes,
    if bullSlingshotSticky and isStrong then "Strong Thrust *"
    else if bearSlingshotSticky and isStrong then "Strong Thrust *"
    else if bullSlingshotSticky then "Thrust *"
    else if bearSlingshotSticky then "Thrust *"
    else if isStrong then "Strong Thrust"
    else if thrust == 1 or thrust == -1 then "Thrust"
    else "",
    if thrust == 1 or bullSlingshotSticky then CreateColor(0, 191, 0)
    else if thrust == -1 or bearSlingshotSticky then Color.RED
    else Color.GRAY
);

################# Aligned Label

def BullCycle = SlowD > SlowD_X;
def BearCycle = SlowD < SlowD_X;
AddLabel((thrust == 1 and BullCycle) or (thrust == -1 and BearCycle), "Confirmed",
    if BullCycle then GlobalColor("Bull")
    else if BearCycle then GlobalColor("Bear")
    else GlobalColor("Neutral"));
def not_confirmed_thrust = !(thrust == 1 and BullCycle) and !(thrust == -1 and BearCycle);

AddLabel(not_confirmed_thrust, "Unconfirmed", Color.GRAY);

################# Extreme Label

def BullCycle2 = SlowD_X > 80;
def BearCycle2 = SlowD_X < 20;

AddLabel(BullCycle2 or BearCycle2, "Extreme", if BullCycle2 then GlobalColor("Bull2") else GlobalColor("Bear2"));

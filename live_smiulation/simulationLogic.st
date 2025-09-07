PROGRAM Main
VAR
    (* Physical I/O - Phase 1 simulation coils *)
    Pump AT %QX0.0 : BOOL := FALSE;
    Filter AT %QX0.1 : BOOL := FALSE;
    UVReactor AT %QX0.2 : BOOL := FALSE;
    StartButton AT %QX0.3 : BOOL := FALSE;       
    EmergencyButton AT %QX0.4 : BOOL := FALSE;   
    LowLevelSensor AT %QX0.5 : BOOL := TRUE;   
    GreenLight AT %QX0.6 : BOOL := FALSE;
    OrangeLight AT %QX0.7 : BOOL := FALSE;
    RedLight AT %QX1.0 : BOOL := FALSE;
    FaultLight AT %QX1.1 : BOOL := FALSE;
    PT_Alert AT %QX1.2 : BOOL := FALSE;
    FT_Alert AT %QX1.3 : BOOL := FALSE;
    Turbidity_Alert AT %QX1.4 : BOOL := FALSE;
    
    (* Phase 2 - Simulation control coils for memory registers *)
    PT_Inc_Sim AT %QX2.0 : BOOL := FALSE;     (* Increment pressure *)
    PT_Dec_Sim AT %QX2.1 : BOOL := FALSE;     (* Decrement pressure *)
    FT_Inc_Sim AT %QX2.2 : BOOL := FALSE;     (* Increment flow *)
    FT_Dec_Sim AT %QX2.3 : BOOL := FALSE;     (* Decrement flow *)
    Turb_Inc_Sim AT %QX2.4 : BOOL := FALSE;   (* Increment turbidity *)
    Turb_Dec_Sim AT %QX2.5 : BOOL := FALSE;   (* Decrement turbidity *)
    Level_Inc_Sim AT %QX2.6 : BOOL := FALSE;  (* Increment water level *)
    Level_Dec_Sim AT %QX2.7 : BOOL := FALSE;  (* Decrement water level *)
END_VAR
VAR
    (* Timer variables *)
    FilterTON_Delay : TIME := T#6s;
    UVReactorTON_Delay : TIME := T#6s;
    FilterTimer : TON;
    UVReactorTimer : TON;
    
    (* System state variables *)
    PumpIsRunning : BOOL := FALSE;
    SystemFault : BOOL := FALSE;
    
    (* Phase 2 - Memory registers for analog values *)
END_VAR
VAR
    Pressure_Value AT %MW0 : INT := 50;        (* 0-100 bar *)
    Flow_Value AT %MW1 : INT := 25;            (* 0-100 L/min *)
    Turbidity_Value AT %MW2 : INT := 5;        (* 0-100 NTU *)
    Water_Level AT %MW3 : INT := 75;           (* 0-100% *)
    
END_VAR
VAR
    (* Thresholds for alerts *)
    PT_Low_Threshold : INT := 20;              (* Low pressure threshold *)
    PT_High_Threshold : INT := 80;             (* High pressure threshold *)
    FT_Low_Threshold : INT := 10;              (* Low flow threshold *)
    Turb_High_Threshold : INT := 15;           (* High turbidity threshold *)
    Level_Low_Threshold : INT := 20;           (* Low level threshold *)
END_VAR
VAR
    (* Edge detection for simulation coils *)
    PT_Inc_R_TRIG : R_TRIG;
    PT_Dec_R_TRIG : R_TRIG;
    FT_Inc_R_TRIG : R_TRIG;
    FT_Dec_R_TRIG : R_TRIG;
    Turb_Inc_R_TRIG : R_TRIG;
    Turb_Dec_R_TRIG : R_TRIG;
    Level_Inc_R_TRIG : R_TRIG;
    Level_Dec_R_TRIG : R_TRIG;
END_VAR

(* Phase 2 - Simulation Logic for Memory Registers *)
(* Pressure simulation *)
PT_Inc_R_TRIG(CLK := PT_Inc_Sim);
PT_Dec_R_TRIG(CLK := PT_Dec_Sim);
IF PT_Inc_R_TRIG.Q AND Pressure_Value < 100 THEN
    Pressure_Value := Pressure_Value + 5;
END_IF;
IF PT_Dec_R_TRIG.Q AND Pressure_Value > 0 THEN
    Pressure_Value := Pressure_Value - 5;
END_IF;

(* Flow simulation *)
FT_Inc_R_TRIG(CLK := FT_Inc_Sim);
FT_Dec_R_TRIG(CLK := FT_Dec_Sim);
IF FT_Inc_R_TRIG.Q AND Flow_Value < 100 THEN
    Flow_Value := Flow_Value + 5;
END_IF;
IF FT_Dec_R_TRIG.Q AND Flow_Value > 0 THEN
    Flow_Value := Flow_Value - 5;
END_IF;

(* Turbidity simulation *)
Turb_Inc_R_TRIG(CLK := Turb_Inc_Sim);
Turb_Dec_R_TRIG(CLK := Turb_Dec_Sim);
IF Turb_Inc_R_TRIG.Q AND Turbidity_Value < 100 THEN
    Turbidity_Value := Turbidity_Value + 2;
END_IF;
IF Turb_Dec_R_TRIG.Q AND Turbidity_Value > 0 THEN
    Turbidity_Value := Turbidity_Value - 2;
END_IF;

(* Water level simulation *)
Level_Inc_R_TRIG(CLK := Level_Inc_Sim);
Level_Dec_R_TRIG(CLK := Level_Dec_Sim);
IF Level_Inc_R_TRIG.Q AND Water_Level < 100 THEN
    Water_Level := Water_Level + 5;
END_IF;
IF Level_Dec_R_TRIG.Q AND Water_Level > 0 THEN
    Water_Level := Water_Level - 5;
END_IF;

(* Generate alerts based on memory register values *)
PT_Alert := (Pressure_Value < PT_Low_Threshold) OR (Pressure_Value > PT_High_Threshold);
FT_Alert := Flow_Value < FT_Low_Threshold;
Turbidity_Alert := Turbidity_Value > Turb_High_Threshold;
LowLevelSensor := Water_Level > Level_Low_Threshold;

(* Original Phase 1 Logic *)
SystemFault := PT_Alert OR FT_Alert OR Turbidity_Alert OR NOT LowLevelSensor;

(* --- PUMP --- *)
PumpIsRunning := (NOT EmergencyButton) AND LowLevelSensor AND (PumpIsRunning OR StartButton);
Pump := PumpIsRunning AND NOT SystemFault;

(* --- FILTER --- *)
FilterTimer(EN := TRUE, IN := Pump, PT := FilterTON_Delay);
Filter := FilterTimer.Q AND Pump AND NOT PT_Alert;

(* --- UV REACTOR --- *)
UVReactorTimer(EN := TRUE, IN := Filter, PT := UVReactorTON_Delay);
UVReactor := UVReactorTimer.Q AND Pump AND NOT Turbidity_Alert;

(* --- LIGHTS --- *)
FaultLight := SystemFault;
GreenLight := Pump AND NOT SystemFault;
OrangeLight := Filter AND NOT SystemFault;
RedLight := UVReactor AND NOT SystemFault;

END_PROGRAM

CONFIGURATION Config0
RESOURCE Res0 ON PLC
    TASK task0(INTERVAL := T#20ms, PRIORITY := 0);
    PROGRAM instance0 WITH task0 : Main;
END_RESOURCE
END_CONFIGURATION
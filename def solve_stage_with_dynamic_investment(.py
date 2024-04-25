from cplex import Cplex
import cplex
from docplex.mp.model import Model
import pandas as pd
import numpy as np
import time
import sys
import random
import openpyxl

generated_data_path = None
realised_uncertainties_path = None
#realised_uncertainties_path = r'C:\Users\rmatta\Desktop\Thesis\Rolling Horizon\realised_uncertainties.xlsx'
#generated_data_path = r'C:\Users\rmatta\Desktop\Thesis\Rolling Horizon\generated_data.csv'

if not generated_data_path or not realised_uncertainties_path:
    print(f'Please set up paths')
    sys.exit(1)

generated_data_df = pd.read_csv(generated_data_path)

# Assuming 'Stage', 'Day', and 'Hour' span consecutive, complete ranges
max_stage = generated_data_df['Stage'].max()
max_day = generated_data_df['Day'].max()
max_hour = generated_data_df['Hour'].max()

yh = np.zeros((max_stage + 1, max_day + 1, max_hour + 1))
yep = np.zeros((max_stage + 1, max_day + 1, max_hour + 1))
ypv = np.zeros((max_stage + 1, max_day + 1, max_hour + 1))
ywt = np.zeros((max_stage + 1, max_day + 1, max_hour + 1))
ye = np.zeros((max_stage + 1, max_day + 1, max_hour + 1))

# Populate the arrays
for _, row in generated_data_df.iterrows():
    # Assuming your stages, days, and hours start from 1
    stage = int(row['Stage'])
    day = int(row['Day'])
    hour = int(row['Hour'])

    # Populate arrays with the corresponding values
    ye[stage, day, hour] = row['Electricity Load']
    ywt[stage, day, hour] = row['WT']
    ypv[stage, day, hour] = row['PV']
    yh[stage, day, hour] = row['Hydrogen Load']



def extract_matrix(realised_uncertainties_path, sheet_name, start_col, end_col, start_row=0, end_row=5):
    # Read the specified sheet
    df = pd.read_excel(realised_uncertainties_path, sheet_name=sheet_name)
    # Extract the matrix as a numpy array
    return df.iloc[start_row:end_row, start_col:end_col].to_numpy(dtype=float)


D = range(1, 19)  # 18 days as integers
K = range(1, 7)   # Devices available
T = range(1, 25)  # 24 time periods as integers
N = range(1,7) # Electrolysers available

Tmax=24 # Hours in a day
TSmax=3
Smax=2 # Number of Stages
Dmax=365 # Number of days in a year
Nmax=18 # Set of representative days
CapMaxBA=10 # KW - Adjusted for realistic battery capacity .. was 10
CapMaxSHST=10 # KW - Adjusted for realistic hydrogen storage capacity .. was 10
CapMaxPV=8000 # KW - Adjusted for a more realistic solar PV capacity
CapMaxWind=10# KW - Adjusted for a more realistic wind turbine capacity .. was 5
Ir=0.05 # Interest rate - Slightly increased to reflect current economic conditions
PenaltyElectricity=0.01 # Unit penalty cost of non-served electricity load - Increased to emphasize reliability
PenaltyHydrogen=0.03 # Unit penalty cost of non-served hydrogen load - Increased to emphasize reliability 0.25
ElectrolyzersAvailable=6#  Increased available electrolyzers for scalability
DeviceIndex=4
nbOfScenarios=2
Kmax=6 # Units available to buy for each device
hprice1=0.385 # 0.385
eprice1=0.289
budgetHN= 10000000
budgetWS= 10000000
CapPV0 = 1500
CapWT0 = 1
total_profit = 0
planning_horizon=15



ElectrolyzerParams = {
    "PTH1": {"Lifetime": 3, "Capacity": 5000, "MaxEPI": 600, "MinEPI": 150, "ElectricityInputStandbyState": 0.05,
             "a1": 0.9, "a2": 0.5, "InvestmentCost": 400000, "MaintenanceCost": 0.01, "OperationCost": 0.005, "EnergyRetention": 0.9}
}

PVParams = {
    "PV1": {"Lifetime": 3, "InvestmentCost": 500, "MaintenanceCost": 0.005, "OperationCost": 0.003, "Efficiency": 0.8}
}

WindParams = {
    "WT1": {"Lifetime": 3, "InvestmentCost": 1500000, "MaintenanceCost": 0.01, "OperationCost": 0.005, "Efficiency": 0.9, "ConversionFactor": 0.0002, "BladeLength": 40}
}

BatteryParams = {
    "BA1": {"Lifetime": 3, "Capacity": 2060, "ChargeEfficiency": 0.9, "PowerCapacityRatio": 0.1,
            "InvestmentCost": 100000, "MaintenanceCost": 0.008, "OperationCost": 0.006}
    
}

HydrogenTankParams = {
    "SHST1": {"Lifetime": 3, "Capacity": 10000, "ChargeEfficiency": 0.9, "PowerCapacityRatio": 0.1, "InvestmentCost": 300000,
              "MaintenanceCost": 0.008, "OperationCost": 0.006}
}


models = {}  # Dictionary to hold model instances



def solve_node(supplier_number_PTH, supplier_number_HT,supplier_number_BA,supplier_number_PV,supplier_number_WT,stage, nb_of_scenarios, node, starting_electrolysers, starting_tanks, starting_batteries, starting_solar_power, starting_wind_power):

    sheet_name=f'Stage {stage} Node {node}'
    ruPVWT = extract_matrix(realised_uncertainties_path,sheet_name, 1, 2, 0, nb_of_scenarios+1)  # B2:C5
    ruPTH = extract_matrix(realised_uncertainties_path,sheet_name,2 ,3, 0, nb_of_scenarios+1)  # E2:F5
    ruBASHST = extract_matrix(realised_uncertainties_path, sheet_name,3, 4, 0, nb_of_scenarios+1)  # H2:I5
    ruELOAD = extract_matrix(realised_uncertainties_path, sheet_name,4, 5, 0, nb_of_scenarios+1)  # K2:L5
    ruHLOAD = extract_matrix(realised_uncertainties_path,sheet_name, 5, 6, 0, nb_of_scenarios+1)  # N2:O5
    hprice = extract_matrix(realised_uncertainties_path, sheet_name,6, 7, 0, nb_of_scenarios+1)  # S2:T5
    eprice = extract_matrix(realised_uncertainties_path,sheet_name, 7, 8, 0, nb_of_scenarios+1)  # V2:W5
    scenario_prob = extract_matrix(realised_uncertainties_path, sheet_name, 8, 9,  0, nb_of_scenarios+1)
    print(f'Solving for new node')
    print(f'*******************************************************************************************')
   
    S = range(1, nb_of_scenarios+1)  # of scenarios

    ruPVWT_1 = ruPVWT[0,0]
    ruPTH_1 = ruPTH[0,0]
    ruBASHST_1 = ruBASHST[0,0]
    ruELOAD_1 = ruELOAD[0,0]
    ruHLOAD_1 = ruHLOAD[0,0]
    hprice1 = hprice[0,0]
    eprice1 = eprice[0,0]
    
    
    ruPVWT_2= np.zeros(nb_of_scenarios+1)
    ruPTH_2= np.zeros(nb_of_scenarios+1)
    ruBASHST_2= np.zeros(nb_of_scenarios+1)
    ruELOAD_2= np.zeros(nb_of_scenarios+1)
    ruHLOAD_2= np.zeros(nb_of_scenarios+1)
    hprice_2= np.zeros(nb_of_scenarios+1)
    eprice_2= np.zeros(nb_of_scenarios+1)
    scenario_probability= np.zeros(nb_of_scenarios+1)

    for s in S:
        #You need to re-initialize these    
        ruPVWT_2[s] = ruPVWT[s, 0]
        ruPTH_2[s] = ruPTH[s, 0]
        ruBASHST_2[s] = ruBASHST[s, 0]
        ruELOAD_2[s] = ruELOAD[s, 0]
        ruHLOAD_2[s] = ruHLOAD[s, 0]
        hprice_2[s] = hprice[s, 0]
        eprice_2[s] = eprice[s, 0]
        scenario_probability[s]= scenario_prob[s, 0]
    
    master_problem=Model('pb1')

    # Decision Variables with Node Index
    z_pth = master_problem.binary_var_dict(((n) for n in N ), name='z_pth')  # Electrolyzer activation
    P_pth = master_problem.continuous_var_cube(D, T, N, name='P_pth')  # Power output of Electrolyzers
    m_pth = master_problem.continuous_var_cube(D, T, N, name='m_pth')  # Mass of hydrogen produced
    m_pth_load = master_problem.continuous_var_cube(D, T, N, name='m_pth_load')  # Mass of hydrogen produced
    m_pth_ht = master_problem.continuous_var_cube(D, T, N, name='m_pth_ht')  # Mass of hydrogen produced
    added_electrolysers= master_problem.integer_var()
    added_batteries= master_problem.integer_var()
    added_tanks= master_problem.integer_var()
    added_solar_power = master_problem.integer_var()
    added_wind_power = master_problem.integer_var()
    tot_electrolysers= master_problem.integer_var()
    tot_batteries= master_problem.integer_var()
    tot_tanks= master_problem.integer_var()
    tot_solar_power = master_problem.integer_var()
    tot_wind_power = master_problem.integer_var()

    # PV Variables
    P_pv = master_problem.continuous_var_matrix(D, T, name='P_pv')  # Power output of PV
    P_pv_ba = master_problem.continuous_var_matrix(D, T, name='P_pv_ba')  # Power output of PV to battery
    P_pv_h = master_problem.continuous_var_matrix(D, T, name='P_pv_h')  # Power output of PV to hydrogen tank
    P_pv_grid = master_problem.continuous_var_matrix(D, T, name='P_pv_grid')  # Power output of PV to grid
    Cap_pv = master_problem.continuous_var(name='Cap_pv')  # Capacity of PV

    # Wind Turbines Variables
    P_wt = master_problem.continuous_var_matrix(D, T,  name='P_wt')  # Power output of Wind Turbines
    P_wt_ba = master_problem.continuous_var_matrix(D, T, name='P_wt_ba')  # Power output of Wind Turbines to battery
    P_wt_h = master_problem.continuous_var_matrix(D, T, name='P_wt_h')  # Power output of Wind Turbines to hydrogen tank
    P_wt_grid = master_problem.continuous_var_matrix(D, T, name='P_wt_grid')  # Power output of Wind Turbines to grid
    Cap_wt = master_problem.binary_var_dict(((k) for k in K), name='Cap_wt')

    # Battery Variables
    SOC_ba = master_problem.continuous_var_cube(D, T, K, name='SOC_ba')  # State of charge of the Battery
    P_in_ba = master_problem.continuous_var_cube(D, T, K, name='P_in_ba')  # Power input to Battery
    P_out_ba = master_problem.continuous_var_cube(D, T, K, name='P_out_ba')  # Power output from Battery
    P_out_ba_grid = master_problem.continuous_var_cube(D, T, K, name='P_out_ba_grid')  # Power output from Battery to grid
    P_out_ba_h = master_problem.continuous_var_cube(D, T, K, name='P_out_ba_h')  # Power output from Battery to hydrogen system
    Cap_ba = master_problem.binary_var_dict(((k) for k in K), name='Cap_ba')

    # Hydrogen Tank Variables
    SOC_ht = master_problem.continuous_var_cube(D, T, K, name='SOC_ht')  # State of charge of the Hydrogen Tank
    m_in_ht = master_problem.continuous_var_cube(D, T, K, name='m_in_ht')  # Mass input to Hydrogen Tank
    m_out_ht = master_problem.continuous_var_cube(D, T, K, name='m_out_ht')  # Mass output from Hydrogen Tank
    Cap_ht = master_problem.binary_var_dict(((k) for k in K), name='Cap_ht') 

    le = master_problem.continuous_var_matrix(D, T, name='le')  # Power shortfall in electricity
    lh = master_problem.continuous_var_matrix(D, T, name='lh')  # Power shortfall in hydrogen production
    
    z_pth_2 = master_problem.binary_var_dict(((n, s) for n in N for s in S ), name='z_pth_2')  # Electrolyzer activation

    # PV Variables
    P_pv_2 = master_problem.continuous_var_cube(D, T, S, name='P_pv_2')  # Power output of PV
    P_pv_ba_2 = master_problem.continuous_var_cube(D, T, S, name='P_pv_ba_2')  # Power output of PV to battery
    P_pv_h_2 = master_problem.continuous_var_cube(D, T, S, name='P_pv_h_2')  # Power output of PV to hydrogen tank
    P_pv_grid_2 = master_problem.continuous_var_cube(D, T, S, name='P_pv_grid_2')  # Power output of PV to grid
    Cap_pv_2 = master_problem.continuous_var_dict(((s) for s in S), name='Cap_pv_2') 

    # Wind Turbines Variables
    P_wt_2 = master_problem.continuous_var_cube(D, T, S,  name='P_wt_2')  # Power output of Wind Turbines
    P_wt_ba_2 = master_problem.continuous_var_cube(D, T, S, name='P_wt_ba_2')  # Power output of Wind Turbines to battery
    P_wt_h_2 = master_problem.continuous_var_cube(D, T, S, name='P_wt_h_2')  # Power output of Wind Turbines to hydrogen tank
    P_wt_grid_2 = master_problem.continuous_var_cube(D, T, S, name='P_wt_grid_2')  # Power output of Wind Turbines to grid
    Cap_wt_2 = master_problem.binary_var_dict(((k, s) for k in K for s in S), name='Cap_wt_2')

    Cap_ba_2 = master_problem.binary_var_dict(((k, s) for k in K for s in S), name='Cap_ba_2')

    # Hydrogen Tank Variables
    Cap_ht_2 = master_problem.binary_var_dict(((k, s) for k in K for s in S), name='Cap_ht_2') 

    le_2 = master_problem.continuous_var_cube(D, T, S, name='le_2')  # Power shortfall in electricity
    lh_2 = master_problem.continuous_var_cube(D, T, S, name='lh_2')  # Power shortfall in hydrogen production

    # added capacity
    added_electrolysers_2 = master_problem.integer_var_dict(((s) for s in S), name='add_PTH_2')
    added_batteries_2 = master_problem.integer_var_dict(((s) for s in S), name='add_BA_2')
    added_tanks_2 = master_problem.integer_var_dict(((s) for s in S), name='add_SHST_2')
    added_solar_power_2 = master_problem.continuous_var_dict(((s) for s in S), name='add_PV_2')
    added_wind_power_2 = master_problem.integer_var_dict(((s) for s in S), name='add_WT_2')

    # Define the four-dimensional variables for Electrolyzers and Battery system
   # Define the four-dimensional variables for Electrolyzers system
    P_pth_2 = {(d, t, n, s): master_problem.continuous_var(name=f'P_pth_2_{d}_{t}_{n}_{s}')
           for d in D for t in T for n in N for s in S}

    m_pth_2 = {(d, t, n, s): master_problem.continuous_var(name=f'm_pth_2_{d}_{t}_{n}_{s}')
           for d in D for t in T for n in N for s in S}

    m_pth_load_2 = {(d, t, n, s): master_problem.continuous_var(name=f'm_pth_load_2_{d}_{t}_{n}_{s}')
                for d in D for t in T for n in N for s in S}

    m_pth_ht_2 = {(d, t, n, s): master_problem.continuous_var(name=f'm_pth_ht_2_{d}_{t}_{n}_{s}')
              for d in D for t in T for n in N for s in S}

    # Define the four-dimensional variables for Battery system
    SOC_ba_2 = {(d, t, k, s): master_problem.continuous_var(name=f'SOC_ba_2_{d}_{t}_{k}_{s}')
            for d in D for t in T for k in K for s in S}

    P_in_ba_2 = {(d, t, k, s): master_problem.continuous_var(name=f'P_in_ba_2_{d}_{t}_{k}_{s}')
             for d in D for t in T for k in K for s in S}

    P_out_ba_2 = {(d, t, k, s): master_problem.continuous_var(name=f'P_out_ba_2_{d}_{t}_{k}_{s}')
              for d in D for t in T for k in K for s in S}

    P_out_ba_grid_2 = {(d, t, k, s): master_problem.continuous_var(name=f'P_out_ba_grid_2_{d}_{t}_{k}_{s}')
                   for d in D for t in T for k in K for s in S}

    P_out_ba_h_2 = {(d, t, k, s): master_problem.continuous_var(name=f'P_out_ba_h_2_{d}_{t}_{k}_{s}')
                for d in D for t in T for k in K for s in S}

    # Define the four-dimensional variables for Hydrogen Tank system
    SOC_ht_2 = {(d, t, k, s): master_problem.continuous_var(name=f'SOC_ht_2_{d}_{t}_{k}_{s}')
            for d in D for t in T for k in K for s in S}

    m_in_ht_2 = {(d, t, k, s): master_problem.continuous_var(name=f'm_in_ht_2_{d}_{t}_{k}_{s}')
             for d in D for t in T for k in K for s in S}

    m_out_ht_2 = {(d, t, k, s): master_problem.continuous_var(name=f'm_out_ht_2_{d}_{t}_{k}_{s}')
              for d in D for t in T for k in K for s in S}

    
 # Initialize dictionaries to store investment costs for each scenario or stage
    CinvPth2 = {}
    CinvWind2 = {}
    CinvPV2 = {}
    CinvBA2 = {}
    CinvSHST2 = {}
    Cinv2 = {}
    ComPTH2 = {}
    ComWind2 = {}
    ComPV2 = {}
    ComBA2 = {}
    ComSHST2 = {}
    Com2 = {}
    Cpen2 = {}
    Revenue2 = {}
    Profit2 = {}

    # Corrected Investment Costs calculation
    CinvPth = ElectrolyzerParams[f'PTH{supplier_number_PTH}']['InvestmentCost'] * added_electrolysers * (1+ruPTH_1)
    CinvWind = WindParams[f'WT{supplier_number_WT}']['InvestmentCost'] * added_wind_power * (1+ruPVWT_1)# Assuming f'WT{supplier_number_WT}' as key for WindParams
    CinvPV = PVParams[f'PV{supplier_number_PV}']['InvestmentCost'] * added_solar_power * (1+ruPVWT_1) # Assuming f'PV{supplier_number_PV}' as key for PVParams
    CinvBA = BatteryParams[f'BA{supplier_number_BA}']['InvestmentCost'] * added_batteries * (1+ruBASHST_1)  # Assuming f'BA{supplier_number_BA}' as key for BatteryParams
    CinvSHST = HydrogenTankParams[f'SHST{supplier_number_HT}']['InvestmentCost'] * added_tanks * (1+ruBASHST_1) # Assuming f'SHST{supplier_number_HT}' as key for HydrogenTankParams
    Cinv = CinvPth + CinvWind + CinvPV + CinvBA + CinvSHST

    # Corrected Operational and Maintenance Costs for Electrolyzers, and similarly for other components
    ComPTH = 365 / 20 * (sum((ElectrolyzerParams[f'PTH{supplier_number_PTH}']['OperationCost'] * m_pth[d, t, n] +
                            ElectrolyzerParams[f'PTH{supplier_number_PTH}']['MaintenanceCost'] * m_pth[d, t, n])
                            for d in D for t in T for n in N if d > 1 and d < 18 and d not in [5, 7, 12, 14])) + 365 / 10 * (sum(
                            (ElectrolyzerParams[f'PTH{supplier_number_PTH}']['OperationCost'] * m_pth[d, t, n] +
                            ElectrolyzerParams[f'PTH{supplier_number_PTH}']['MaintenanceCost'] * m_pth[d, t, n])
                            for d in D for t in T for n in N if d in [5, 7, 12, 14]))

    # Battery Operational and Maintenance Costs
    ComBA = 365 / 20 * (sum(BatteryParams[f'BA{supplier_number_BA}']['OperationCost'] * (P_in_ba[d, t, k] + P_out_ba[d, t, k])+
                          BatteryParams[f'BA{supplier_number_BA}']['MaintenanceCost'] * (P_in_ba[d, t, k] + P_out_ba[d, t, k])
                          for d in D for t in T for k in K if d > 1 and d < 18 and d not in [5, 7, 12, 14])) + 365 / 10 * (sum((BatteryParams[f'BA{supplier_number_BA}']['OperationCost'] * (P_in_ba[d, t, k] + P_out_ba[d, t, k]) +
                          BatteryParams[f'BA{supplier_number_BA}']['MaintenanceCost'] *(P_in_ba[d, t, k] + P_out_ba[d, t, k]))
                          for d in D for t in T for k in K if d in [5, 7, 12, 14]))


    # Hydrogen Storage Operational and Maintenance Costs
    ComSHST = 365 / 20 * (sum((HydrogenTankParams[f'SHST{supplier_number_HT}']['OperationCost'] * (m_in_ht[d, t, k] + m_out_ht[d, t, k]) +
                            HydrogenTankParams[f'SHST{supplier_number_HT}']['MaintenanceCost'] * (m_in_ht[d, t, k] + m_out_ht[d, t, k]))
                            for d in D for t in T for k in K if d > 1 and d < 18 and d not in [5, 7, 12, 14])) + 365 / 10 * (sum((HydrogenTankParams[f'SHST{supplier_number_HT}']['OperationCost'] * (m_in_ht[d, t, k] + m_out_ht[d, t, k]) +
                            HydrogenTankParams[f'SHST{supplier_number_HT}']['MaintenanceCost'] * (m_in_ht[d, t, k] + m_out_ht[d, t, k]))
                            for d in D for t in T for k in K if d in [5, 7, 12, 14]))

    # PV Systems Operational and Maintenance Costs
    ComPV = 365 / 20 * (sum((PVParams[f'PV{supplier_number_PV}']['OperationCost'] * P_pv[d, t] +
                          PVParams[f'PV{supplier_number_PV}']['MaintenanceCost'] * P_pv[d, t]
                          for d in D for t in T if d > 1 and d < 18 and d not in [5, 7, 12, 14]))) + 365 / 10 * (sum((PVParams[f'PV{supplier_number_PV}']['OperationCost'] * P_pv[d, t] +
                          PVParams[f'PV{supplier_number_PV}']['MaintenanceCost'] * P_pv[d, t]
                          for d in D for t in T if d in [5, 7, 12, 14])))

    # Wind Turbines Operational and Maintenance Costs
    ComWind = 365 / 20 * (sum((WindParams[f'WT{supplier_number_WT}']['OperationCost'] * P_wt[d, t] +
                          WindParams[f'WT{supplier_number_WT}']['MaintenanceCost'] * P_wt[d, t])
                          for d in D for t in T if d > 1 and d < 18 and d not in [5, 7, 12, 14])) + 365 / 10 * (sum((WindParams[f'WT{supplier_number_WT}']['OperationCost'] * P_wt[d, t] +
                          WindParams[f'WT{supplier_number_WT}']['MaintenanceCost'] * P_wt[d, t])
                          for d in D for t in T if d in [5, 7, 12, 14]))

    # Total Component-wise Costs
    Com = ComPTH + ComWind + ComPV + ComBA + ComSHST


    # Penalties calculation
    Cpen = 365 / 20 * (sum((PenaltyElectricity * le[d, t] + PenaltyHydrogen * lh[d, t]) 
                        for d in D for t in T if d > 1 and d < 18 and d not in [5, 7, 12, 14])) + 365 / 10 * (sum((PenaltyElectricity * le[d, t] + PenaltyHydrogen * lh[d, t]) 
                        for d in D for t in T if d in [5, 7, 12, 14]))

    # Revenue calculation
    Revenue = 365 / 20 * (
        sum(m_pth_load[d, t, n] * hprice1 
            for d in D for t in T for n in N if 1 < d < 18 and d not in [5, 7, 12, 14])
        + sum((m_out_ht[d, t, k] * hprice1 + P_out_ba_grid[d, t, k] * eprice1) 
            for d in D for t in T for k in K if 1 < d < 18 and d not in [5, 7, 12, 14])
        + sum((P_pv_grid[d, t] + P_wt_grid[d, t]) * eprice1 
            for d in D for t in T if 1 < d < 18 and d not in [5, 7, 12, 14])
        ) + 365 / 10 * (sum(m_pth_load[d, t, n] * hprice1 
            for d in D for t in T for n in N if d in [5, 7, 12, 14])
        + sum((m_out_ht[d, t, k] * hprice1 + P_out_ba_grid[d, t, k] * eprice1) 
            for d in D for t in T for k in K if d in [5, 7, 12, 14])
        + sum((P_pv_grid[d, t] + P_wt_grid[d, t]) * eprice1 
            for d in D for t in T if d in [5, 7, 12, 14])
        )


    # Profit calculation
    Profit_HN = Revenue - Cpen - Cinv - Com

    for s in S:
        CinvPth2[s] = ElectrolyzerParams[f'PTH{supplier_number_PTH}']['InvestmentCost'] * added_electrolysers_2[s] * (1+ruPTH_2[s])/((1+Ir)**(stage-1))
        CinvWind2[s] = WindParams[f'WT{supplier_number_WT}']['InvestmentCost'] * added_wind_power_2[s] * (1+ruPVWT_2[s])/((1+Ir)**(stage-1))
        CinvPV2[s] = PVParams[f'PV{supplier_number_PV}']['InvestmentCost'] * added_solar_power_2[s] *  (1+ruPVWT_2[s])/((1+Ir)**(stage-1))
        CinvBA2[s] = BatteryParams[f'BA{supplier_number_BA}']['InvestmentCost'] * added_batteries_2[s] *  (1+ruBASHST_2[s])/((1+Ir)**(stage-1))
        CinvSHST2[s] = HydrogenTankParams[f'SHST{supplier_number_HT}']['InvestmentCost'] * added_tanks_2[s] * (1+ruBASHST_2[s])/((1+Ir)**(stage-1))
        Cinv2[s] = scenario_probability[s]* (CinvPth2[s] + CinvWind2[s] + CinvPV2[s] + CinvBA2[s] + CinvSHST2[s])

    
   
        # Corrected Operational and Maintenance Costs for Electrolyzers, and similarly for other components
        ComPTH2[s] = 365 / 20 * (sum((ElectrolyzerParams[f'PTH{supplier_number_PTH}']['OperationCost'] * m_pth_2[d, t, n, s] +
                                ElectrolyzerParams[f'PTH{supplier_number_PTH}']['MaintenanceCost'] * m_pth_2[d, t, n, s])
                                for d in D for t in T for n in N if d > 1 and d < 18 and d not in [5, 7, 12, 14]))+ 365 / 10 * (sum(
                                (ElectrolyzerParams[f'PTH{supplier_number_PTH}']['OperationCost'] * m_pth_2[d, t, n, s] +
                                ElectrolyzerParams[f'PTH{supplier_number_PTH}']['MaintenanceCost'] * m_pth_2[d, t, n, s])
                                for d in D for t in T for n in N  if d in [5, 7, 12, 14]))

        # Battery Operational and Maintenance Costs
        ComBA2[s] = 365 / 20 * (sum(BatteryParams[f'BA{supplier_number_BA}']['OperationCost'] * (P_in_ba_2[d, t, k, s] + P_out_ba_2[d, t, k, s])+
                                BatteryParams[f'BA{supplier_number_BA}']['MaintenanceCost'] * (P_in_ba_2[d, t, k, s] + P_out_ba_2[d, t, k, s])
                                for d in D for t in T for k in K if d > 1 and d < 18 and d not in [5, 7, 12, 14])) + 365 / 10 * (sum((BatteryParams[f'BA{supplier_number_BA}']['OperationCost'] * (P_in_ba_2[d, t, k, s] + P_out_ba_2[d, t, k, s]) +
                                BatteryParams[f'BA{supplier_number_BA}']['MaintenanceCost'] *(P_in_ba_2[d, t, k, s] + P_out_ba_2[d, t, k, s]))
                                for d in D for t in T for k in K if d in [5, 7, 12, 14]))

        # Hydrogen Storage Operational and Maintenance Costs
        ComSHST2[s] = 365 / 20 * (sum((HydrogenTankParams[f'SHST{supplier_number_HT}']['OperationCost'] * (m_in_ht_2[d, t, k, s] + m_out_ht_2[d, t, k, s]) +
                                HydrogenTankParams[f'SHST{supplier_number_HT}']['MaintenanceCost'] * (m_in_ht_2[d, t, k, s] + m_out_ht_2[d, t, k, s]))
                                for d in D for t in T for k in K if d > 1 and d < 18 and d not in [5, 7, 12, 14])) + 365 / 10 * (sum((HydrogenTankParams[f'SHST{supplier_number_HT}']['OperationCost'] * (m_in_ht_2[d, t, k, s] + m_out_ht_2[d, t, k, s]) +
                                HydrogenTankParams[f'SHST{supplier_number_HT}']['MaintenanceCost'] * (m_in_ht_2[d, t, k, s] + m_out_ht_2[d, t, k, s]))
                                for d in D for t in T for k in K if d in [5, 7, 12, 14]))

        # PV Systems Operational and Maintenance Costs
        ComPV2[s] = 365 / 20 * (sum((PVParams[f'PV{supplier_number_PV}']['OperationCost'] * P_pv_2[d, t, s] +
                            PVParams[f'PV{supplier_number_PV}']['MaintenanceCost'] * P_pv_2[d, t, s]
                            for d in D for t in T if d > 1 and d < 18 and d not in [5, 7, 12, 14]))) + 365 / 10 * (sum((PVParams[f'PV{supplier_number_PV}']['OperationCost'] * P_pv_2[d, t, s] +
                            PVParams[f'PV{supplier_number_PV}']['MaintenanceCost'] * P_pv_2[d, t, s]
                            for d in D for t in T if d in [5, 7, 12, 14])))

        # Wind Turbines Operational and Maintenance Costs
        ComWind2[s] = 365 / 20 * (sum((WindParams[f'WT{supplier_number_WT}']['OperationCost'] * P_wt_2[d, t, s] +
                            WindParams[f'WT{supplier_number_WT}']['MaintenanceCost'] * P_wt_2[d, t, s])
                            for d in D for t in T if d > 1 and d < 18 and d not in [5, 7, 12, 14])) + 365 / 10 * (sum((WindParams[f'WT{supplier_number_WT}']['OperationCost'] * P_wt_2[d, t, s] +
                            WindParams[f'WT{supplier_number_WT}']['MaintenanceCost'] * P_wt_2[d, t, s])
                            for d in D for t in T if d in [5, 7, 12, 14]))

        # Total Component-wise Costs
        #Com2[s] = (planning_horizon-stage+1) * (scenario_probability[s]*(ComPTH2[s] + ComWind2[s] + ComPV2[s] + ComBA2[s] + ComSHST2[s]))
        Com2[s] = (scenario_probability[s]*(ComPTH2[s] + ComWind2[s] + ComPV2[s] + ComBA2[s] + ComSHST2[s]))

        # Penalties calculation
        Cpen2[s] = (scenario_probability[s]*(365 / 20 * (sum((PenaltyElectricity * le_2[d, t, s] + PenaltyHydrogen * lh_2[d, t, s]) 
                        for d in D for t in T if d > 1 and d < 18 and d not in [5, 7, 12, 14])) + 365 / 10 * (sum((PenaltyElectricity * le_2[d, t, s] + PenaltyHydrogen * lh_2[d, t, s]) 
                        for d in D for t in T if d in [5, 7, 12, 14]))))
    # Revenue calculation
        # Revenue calculation
        Revenue2[s] =scenario_probability[s]* (365 / 20 * (
            sum(m_pth_load_2[d, t, n, s] * hprice_2[s]
                for d in D for t in T for n in N if 1 < d < 18 and d not in [5, 7, 12, 14])
            + sum((m_out_ht_2[d, t, k, s] * hprice_2[s]  + P_out_ba_grid_2[d, t, k, s] * eprice_2[s]) 
                for d in D for t in T for k in K if 1 < d < 18 and d not in [5, 7, 12, 14])
            + sum((P_pv_grid_2[d, t, s] + P_wt_grid_2[d, t, s]) * eprice_2[s] 
                for d in D for t in T if 1 < d < 18 and d not in [5, 7, 12, 14])
            ) + 365 / 10 * (sum(m_pth_load_2[d, t, n, s] * hprice_2[s]  
                for d in D for t in T for n in N  if d in [5, 7, 12, 14])
            + sum((m_out_ht_2[d, t, k, s] * hprice_2[s]  + P_out_ba_grid_2[d, t, k, s] * eprice_2[s]) 
                for d in D for t in T for k in K if d in [5, 7, 12, 14])
            + sum((P_pv_grid_2[d, t, s] + P_wt_grid_2[d, t, s]) * eprice_2[s]
                for d in D for t in T if d in [5, 7, 12, 14])
        ))
        # Profit calculation
        Profit2[s] = Revenue2[s] - Cpen2[s] - Cinv2[s] - Com2[s]
        #actual_profit[s] = Revenue[s] - Cpen[s] - actual_investment_cost[s] - Com[s]


    # Define the objective function (assuming cost coefficients c_n and probability p_n)
    master_problem.maximize(Profit_HN+master_problem.sum(Profit2[s] for s in S))
    for d in D:
        for t in T:  # Assuming 'e' represents different electrolyzers if needed
            for n in N:
                # Electrolyzer Constraints
                master_problem.add_constraint(P_pth[d, t, n] <= ElectrolyzerParams[f'PTH{supplier_number_PTH}']['MaxEPI'] * z_pth[n], f'P_pth_dynamic_{d}_{t}_{n}') 
                master_problem.add_constraint(m_pth[d, t, n] <= ElectrolyzerParams[f'PTH{supplier_number_PTH}']['a1'] * P_pth[d, t, n], f'm_pth_dynamic_{d}_{t}_{n}')
                master_problem.add_constraint(m_pth[d, t, n] == m_pth_load[d, t, n] + m_pth_ht[d, t, n], f'm_pth_balance_{d}_{t}_{n}')
                
    # PV and WT Capacity and Power Output Constraints
    for d in D:
        for t in T: 
            for k in K:
                master_problem.add_constraint(m_in_ht[d, t, k] <= HydrogenTankParams[f'SHST{supplier_number_HT}']['PowerCapacityRatio']* HydrogenTankParams[f'SHST{supplier_number_HT}']['Capacity'] * Cap_ht[k], f'm_in_ht_max_{d}_{t}_{k}')
                master_problem.add_constraint(m_out_ht[d, t, k] <= SOC_ht[d, t, k], f'm_out_ht_max_{d}_{t}_{k}')
                master_problem.add_constraint(m_out_ht[d, t, k] <= HydrogenTankParams[f'SHST{supplier_number_HT}']['PowerCapacityRatio'] *HydrogenTankParams[f'SHST{supplier_number_HT}']['Capacity']* Cap_ht[k], f'm_out_ht_limit_{d}_{t}_{k}')
                master_problem.add_constraint(SOC_ht[d, t, k] <= HydrogenTankParams[f'SHST{supplier_number_HT}']['Capacity']* Cap_ht[k], f'SOC_ht_max_{d}_{t}_{k}')

                master_problem.add_constraint(P_in_ba[d, t, k] <= BatteryParams[f'BA{supplier_number_BA}']['PowerCapacityRatio'] *BatteryParams[f'BA{supplier_number_BA}']['Capacity']* Cap_ba[k], f'P_in_ba_limit_{d}_{t}_{k}')
                master_problem.add_constraint(P_out_ba[d, t, k] <= SOC_ba[d, t, k], f'm_out_ht_SOC_limit_{d}_{t}_{k}')
                master_problem.add_constraint(P_out_ba[d, t, k] <= BatteryParams[f'BA{supplier_number_BA}']['PowerCapacityRatio'] *BatteryParams[f'BA{supplier_number_BA}']['Capacity']* Cap_ba[k], f'P_in_ba_limit_{d}_{t}_{k}')
                master_problem.add_constraint(SOC_ba[d, t, k] <= BatteryParams[f'BA{supplier_number_BA}']['Capacity']* Cap_ba[k], f'SOC_ba_max_{d}_{t}_{k}')
                master_problem.add_constraint(P_out_ba[d, t, k] == P_out_ba_grid[d, t, k] + P_out_ba_h[d, t, k])

                if t > 1:
                    master_problem.add_constraint(SOC_ba[d, t, k] == SOC_ba[d, t-1, k] + (P_in_ba[d, t, k] * BatteryParams[f'BA{supplier_number_BA}']['ChargeEfficiency']) - (P_out_ba[d, t, k] / BatteryParams[f'BA{supplier_number_BA}']['ChargeEfficiency']), f'SOC_ba_dynamic_{d}_{t}_{k}')
                    master_problem.add_constraint(SOC_ht[d, t, k] == SOC_ht[d, t-1, k] + (m_in_ht[d, t, k] * HydrogenTankParams[f'SHST{supplier_number_HT}']['ChargeEfficiency']) - (m_out_ht[d, t, k] / HydrogenTankParams[f'SHST{supplier_number_HT}']['ChargeEfficiency']), f'SOC_ht_dynamic_{d}_{t}_{k}')

    # Battery Constraints
    for d in D:
        for t in T:
            master_problem.add_constraint(P_wt[d, t] <= ywt[stage-1, d, t]**3 * master_problem.sum(Cap_wt[k] for k in K) * WindParams[f'WT{supplier_number_WT}']['BladeLength']**2 * WindParams[f'WT{supplier_number_WT}']['ConversionFactor'] * WindParams[f'WT{supplier_number_WT}']['Efficiency'])
            master_problem.add_constraint(P_wt[d, t] == P_wt_grid[d, t] + P_wt_h[d, t] + P_wt_ba[d, t], f'P_wt_distribution_{d}_{t}')
            master_problem.add_constraint(P_wt_grid[d, t] + master_problem.sum(P_out_ba_grid[d, t, k] for k in K) + P_pv_grid[d, t] == ye[stage-1, d, t]* (1+ruELOAD_1)-le[d, t])
            master_problem.add_constraint(master_problem.sum(m_pth_load[d, t, n] for n in N) + master_problem.sum(m_out_ht[d, t, k] for k in K) == yh[stage-1, d, t] * (1+ruHLOAD_1)-lh[d, t])
            master_problem.add_constraint(P_pv[d, t] <= ypv[stage-1, d, t] * Cap_pv * PVParams[f'PV{supplier_number_PV}']['Efficiency'], f'P_pv_capacity_{d}_{t}')
            master_problem.add_constraint(P_pv[d, t] == P_pv_grid[d, t] + P_pv_h[d, t] + P_pv_ba[d, t], f'P_pv_distribution_{d}_{t}')
            master_problem.add_constraint(master_problem.sum(m_in_ht[d, t, k] for k in K) ==  master_problem.sum(m_pth_ht[d, t, n] for n in N))
            master_problem.add_constraint(master_problem.sum(P_in_ba[d, t, k] for k in K) ==  P_pv_ba[d, t] + P_wt_ba[d, t])
            master_problem.add_constraint(master_problem.sum(P_pth[d, t, n] for n in N) == ElectrolyzerParams[f'PTH{supplier_number_PTH}']['EnergyRetention']*(P_pv_h[d, t] + P_wt_h[d, t] + master_problem.sum(P_out_ba_h[d, t, k] for k in K)))

    for d in D:
        for k in K:
            if d > 1:
                master_problem.add_constraint(SOC_ba[d, 1, k] == SOC_ba[d-1, 24, k] + P_in_ba[d, 1, k] * BatteryParams[f'BA{supplier_number_BA}']['ChargeEfficiency'] - P_out_ba[d, 1, k] / BatteryParams[f'BA{supplier_number_BA}']['ChargeEfficiency'], f'SOC_ba_continuity_{d}_{k}')
                master_problem.add_constraint(SOC_ht[d, 1, k] == SOC_ht[d-1, 24, k]+ m_in_ht[d,1,k] * HydrogenTankParams[f'SHST{supplier_number_HT}']['ChargeEfficiency'] - m_out_ht[d,1,k] / HydrogenTankParams[f'SHST{supplier_number_HT}']['ChargeEfficiency'], f'SOC_ht_continuity_{d}_{k}')
            
                

    for k in K:
        master_problem.add_constraint(SOC_ht[1, 1, k] == m_in_ht[1, 1, k] * HydrogenTankParams[f'SHST{supplier_number_HT}']['ChargeEfficiency'] - m_out_ht[1, 1, k] / HydrogenTankParams[f'SHST{supplier_number_HT}']['ChargeEfficiency'])
        master_problem.add_constraint(SOC_ba[1, 1, k] == P_in_ba[1, 1, k] * BatteryParams[f'BA{supplier_number_BA}']['ChargeEfficiency'] - P_out_ba[1, 1, k] / BatteryParams[f'BA{supplier_number_BA}']['ChargeEfficiency'])
        if k > 1:
            master_problem.add_constraint(Cap_ba[k-1] >= Cap_ba[k])
            master_problem.add_constraint(Cap_ht[k-1] >= Cap_ht[k])
            master_problem.add_constraint(Cap_wt[k-1] >= Cap_wt[k])
        


    for n in N:
        if n > 1:
            master_problem.add_constraint(z_pth[n-1] >= z_pth[n], f'sequential_activation_{n}')

    master_problem.add_constraint(master_problem.sum(z_pth[n] for n in N) == starting_electrolysers + added_electrolysers)
    master_problem.add_constraint(master_problem.sum(Cap_ba[k] for k in K) == starting_batteries + added_batteries)
    master_problem.add_constraint(master_problem.sum(Cap_ht[k] for k in K) == starting_tanks + added_tanks)
    master_problem.add_constraint(master_problem.sum(Cap_wt[k] for k in K) == starting_wind_power + added_wind_power)
    master_problem.add_constraint(Cap_pv == starting_solar_power + added_solar_power)
    
    master_problem.add_constraint(master_problem.sum(z_pth[n] for n in N) == tot_electrolysers)
    master_problem.add_constraint(master_problem.sum(Cap_ba[k] for k in K) == tot_batteries)
    master_problem.add_constraint(master_problem.sum(Cap_ht[k] for k in K) == tot_tanks)
    master_problem.add_constraint(master_problem.sum(Cap_wt[k] for k in K) == tot_wind_power)
   

    # Budget Constraint
    master_problem.add_constraint(PVParams[f'PV{supplier_number_PV}']['InvestmentCost'] * added_solar_power * (1+ruPVWT_1) + WindParams[f'WT{supplier_number_WT}']['InvestmentCost'] * added_wind_power* (1+ruPVWT_1) + BatteryParams[f'BA{supplier_number_BA}']['InvestmentCost'] * added_batteries* (1+ruBASHST_1) + HydrogenTankParams[f'SHST{supplier_number_HT}']['InvestmentCost'] * added_tanks * (1+ruBASHST_1) + ElectrolyzerParams[f'PTH{supplier_number_PTH}']['InvestmentCost'] * added_electrolysers* (1+ruPTH_1) <= budgetHN, 'budget_constraint')
   






# Constraints for stage 2
    for d in D:
        for t in T:  # Assuming 'e' represents different electrolyzers if needed
            for n in N:
                for s in S:
                # Electrolyzer Constraints
                    master_problem.add_constraint(P_pth_2[d, t, n, s] <= ElectrolyzerParams[f'PTH{supplier_number_PTH}']['MaxEPI']* z_pth_2[n, s], f'P_pth_dynamic_{d}_{t}_{n}_{s}') 
                    master_problem.add_constraint(m_pth_2[d, t, n, s] <= ElectrolyzerParams[f'PTH{supplier_number_PTH}']['a1'] * P_pth_2[d, t, n, s], f'm_pth_dynamic_{d}_{t}_{n}_{s}')
                    master_problem.add_constraint(m_pth_2[d, t, n, s] == m_pth_load_2[d, t, n, s] + m_pth_ht_2[d, t, n, s], f'm_pth_balance_{d}_{t}_{n}_{s}')
                
    # PV and WT Capacity and Power Output Constraints
    for d in D:
        for t in T: 
            for k in K:
                for s in S:
                    master_problem.add_constraint(m_in_ht_2[d, t, k, s] <= HydrogenTankParams[f'SHST{supplier_number_HT}']['PowerCapacityRatio']* HydrogenTankParams[f'SHST{supplier_number_HT}']['Capacity'] * Cap_ht_2[k, s], f'm_in_ht_max_2_{d}_{t}_{k}_{s}')
                    master_problem.add_constraint(m_out_ht_2[d, t, k, s] <= SOC_ht_2[d, t, k, s], f'm_out_ht_max_2_{d}_{t}_{k}_{s}')
                    master_problem.add_constraint(m_out_ht_2[d, t, k, s] <= HydrogenTankParams[f'SHST{supplier_number_HT}']['PowerCapacityRatio'] * HydrogenTankParams[f'SHST{supplier_number_HT}']['Capacity']* Cap_ht_2[k, s], f'm_out_ht_limit_{d}_{t}_{k}_{s}')
                    master_problem.add_constraint(SOC_ht_2[d, t, k, s] <= HydrogenTankParams[f'SHST{supplier_number_HT}']['Capacity']* Cap_ht_2[k, s], f'SOC_ht_max_{d}_{t}_{k}_{s}')

                    master_problem.add_constraint(P_in_ba_2[d, t, k, s] <= BatteryParams[f'BA{supplier_number_BA}']['PowerCapacityRatio'] *BatteryParams[f'BA{supplier_number_BA}']['Capacity']* Cap_ba_2[k, s], f'P_in_ba_limit_{d}_{t}_{k}_{s}')
                    master_problem.add_constraint(P_out_ba_2[d, t, k, s] <= SOC_ba_2[d, t, k, s], f'm_out_ht_SOC_limit_{d}_{t}_{k}_{s}')
                    master_problem.add_constraint(P_out_ba_2[d, t, k, s] <= BatteryParams[f'BA{supplier_number_BA}']['PowerCapacityRatio'] *BatteryParams[f'BA{supplier_number_BA}']['Capacity']* Cap_ba_2[k, s], f'P_in_ba_limit_{d}_{t}_{k}_{s}')
                    master_problem.add_constraint(SOC_ba_2[d, t, k, s] <= BatteryParams[f'BA{supplier_number_BA}']['Capacity']* Cap_ba_2[k, s], f'SOC_ba_max_{d}_{t}_{k}_{s}')
                    master_problem.add_constraint(P_out_ba_2[d, t, k, s] == P_out_ba_grid_2[d, t, k, s] + P_out_ba_h_2[d, t, k, s], f'P_out_ba_dist_{d}_{t}_{k}_{s}')

                    if t > 1:
                        master_problem.add_constraint(SOC_ba_2[d, t, k, s] == SOC_ba_2[d, t-1, k, s] + (P_in_ba_2[d, t, k, s] * BatteryParams[f'BA{supplier_number_BA}']['ChargeEfficiency']) - (P_out_ba_2[d, t, k, s] / BatteryParams[f'BA{supplier_number_BA}']['ChargeEfficiency']), f'SOC_ba_dynamic_{d}_{t}_{k}_{s}')
                        master_problem.add_constraint(SOC_ht_2[d, t, k, s] == SOC_ht_2[d, t-1, k, s] + (m_in_ht_2[d, t, k, s] * HydrogenTankParams[f'SHST{supplier_number_HT}']['ChargeEfficiency']) - (m_out_ht_2[d, t, k, s] / HydrogenTankParams[f'SHST{supplier_number_HT}']['ChargeEfficiency']), f'SOC_ht_dynamic_{d}_{t}_{k}_{s}')


    # Battery Constraints
    for d in D:
        for t in T:
            for s in S:
                master_problem.add_constraint(P_wt_2[d, t, s] <= ywt[stage, d, t]**3 * master_problem.sum(Cap_wt_2[k, s] for k in K) * WindParams[f'WT{supplier_number_WT}']['BladeLength']**2 * WindParams[f'WT{supplier_number_WT}']['ConversionFactor'] * WindParams[f'WT{supplier_number_WT}']['Efficiency'], f'wind_generation_{d}_{t}_{s}')
                master_problem.add_constraint(P_wt_2[d, t, s] == P_wt_grid_2[d, t, s] + P_wt_h_2[d, t, s] + P_wt_ba_2[d, t, s], f'P_wt_distribution_{d}_{t}_{s}')
                master_problem.add_constraint(P_wt_grid_2[d, t, s] + master_problem.sum(P_out_ba_grid_2[d, t, k, s] for k in K) + P_pv_grid_2[d, t, s] == ye[stage, d, t] * (1+ruELOAD_2[s])-le_2[d, t, s], f'e_load_satisfaction_{d}_{t}_{s}')
                master_problem.add_constraint(master_problem.sum(m_pth_load_2[d, t, n, s] for n in N) + master_problem.sum(m_out_ht_2[d, t, k, s] for k in K) == yh[stage, d, t] * (1+ruHLOAD_2[s])-lh_2[d, t, s], f'h_load_satisfaction_{d}_{t}_{s}')
                master_problem.add_constraint(P_pv_2[d, t, s] <= ypv[stage, d, t] * Cap_pv_2[s] * PVParams[f'PV{supplier_number_PV}']['Efficiency'], f'P_pv_capacity_2_{d}_{t}_{s}')
                master_problem.add_constraint(P_pv_2[d, t, s] == P_pv_grid_2[d, t, s] + P_pv_h_2[d, t, s] + P_pv_ba_2[d, t, s], f'P_pv_distribution_{d}_{t}_{s}')
                master_problem.add_constraint(master_problem.sum(m_in_ht_2[d, t, k, s] for k in K) ==  master_problem.sum(m_pth_ht_2[d, t, n, s] for n in N), f'tank_input_{d}_{t}_{s}')
                master_problem.add_constraint(master_problem.sum(P_in_ba_2[d, t, k, s] for k in K) ==  P_pv_ba_2[d, t, s] + P_wt_ba_2[d, t, s], f'battery_input_{d}_{t}_{s}')
                master_problem.add_constraint(master_problem.sum(P_pth_2[d, t, n, s] for n in N) == ElectrolyzerParams[f'PTH{supplier_number_PTH}']['EnergyRetention']*(P_pv_h_2[d, t, s] + P_wt_h_2[d, t, s] + master_problem.sum(P_out_ba_h_2[d, t, k, s] for k in K)))

    for d in D:
        for k in K:
            for s in S:
                if d > 1:
                    master_problem.add_constraint(SOC_ba_2[d, 1, k, s] == SOC_ba_2[d-1, 24, k, s] + P_in_ba_2[d, 1, k, s] * BatteryParams[f'BA{supplier_number_BA}']['ChargeEfficiency'] - P_out_ba_2[d, 1, k, s] / BatteryParams[f'BA{supplier_number_BA}']['ChargeEfficiency'], f'SOC_ba_continuity_{d}_{k}_{s}')
                    master_problem.add_constraint(SOC_ht_2[d, 1, k, s] == SOC_ht_2[d-1, 24, k, s]+ m_in_ht_2[d,1,k, s] * HydrogenTankParams[f'SHST{supplier_number_HT}']['ChargeEfficiency'] - m_out_ht_2[d,1,k, s] / HydrogenTankParams[f'SHST{supplier_number_HT}']['ChargeEfficiency'], f'SOC_ht_continuity_{d}_{k}_{s}')

    for k in K:
        for s in S:
            master_problem.add_constraint(SOC_ht_2[1, 1, k, s] == m_in_ht_2[1, 1, k, s] * HydrogenTankParams[f'SHST{supplier_number_HT}']['ChargeEfficiency'] - m_out_ht_2[1, 1, k, s] / HydrogenTankParams[f'SHST{supplier_number_HT}']['ChargeEfficiency'], f'SOC_ht_first_hour_{d}_{k}_{s}')
            master_problem.add_constraint(SOC_ba_2[1, 1, k, s] == P_in_ba_2[1, 1, k, s] * BatteryParams[f'BA{supplier_number_BA}']['ChargeEfficiency'] - P_out_ba_2[1, 1, k, s] / BatteryParams[f'BA{supplier_number_BA}']['ChargeEfficiency'], f'SOC_ba_first_hour_{d}_{k}_{s}')
            if k > 1:
                master_problem.add_constraint(Cap_ba_2[k-1, s] >= Cap_ba_2[k, s])
                master_problem.add_constraint(Cap_ht_2[k-1, s] >= Cap_ht_2[k, s])
                master_problem.add_constraint(Cap_wt_2[k-1, s] >= Cap_wt_2[k, s])
        
    for n in N:
        for s in S:
            if n > 1:
                master_problem.add_constraint(z_pth_2[n-1, s] >= z_pth_2[n, s], f'sequential_activation_{n}')

    for s in S:
        master_problem.add_constraint(master_problem.sum(Cap_ba_2[k, s] for k in K) == master_problem.sum(Cap_ba[k] for k in K) + added_batteries_2[s])
        master_problem.add_constraint(master_problem.sum(Cap_ht_2[k, s] for k in K) == master_problem.sum(Cap_ht[k] for k in K)  + added_tanks_2[s])
        master_problem.add_constraint(master_problem.sum(Cap_wt_2[k, s] for k in K) == master_problem.sum(Cap_wt[k] for k in K) + added_wind_power_2[s])
        master_problem.add_constraint(Cap_pv_2[s] == Cap_pv + added_solar_power_2[s])
        master_problem.add_constraint(master_problem.sum(z_pth_2[n, s] for n in N) ==  master_problem.sum(z_pth[n] for n in N)+ added_electrolysers_2[s])
        #master_problem.add_constraint(Cap_pv_2[s] <= CapMaxPV)
        master_problem.add_constraint(PVParams[f'PV{supplier_number_PV}']['InvestmentCost'] * added_solar_power_2[s] * (1+ruPVWT_2[s]) + WindParams[f'WT{supplier_number_WT}']['InvestmentCost'] *(1+ruPVWT_2[s])* added_wind_power_2[s] + BatteryParams[f'BA{supplier_number_BA}']['InvestmentCost'] *(1+ruBASHST_2[s])* added_batteries_2[s] + HydrogenTankParams[f'SHST{supplier_number_HT}']['InvestmentCost'] * (1+ruBASHST_2[s]) * added_tanks_2[s] + ElectrolyzerParams[f'PTH{supplier_number_PTH}']['InvestmentCost'] *(1+ruPTH_2[s])*added_electrolysers_2[s] <= budgetWS, 'budget_constraint')
        
# Note: Adjustments may be needed based on actual variable definitions and the structure of your model.

    # Solve the model
    solution = master_problem.solve()

    if solution:
        

        print(f'Stage 1 solution')
        print(f'Node specific profit: {Profit_HN.solution_value}')
        print(f'added_electrolysers: {added_electrolysers.solution_value}, added_tanks: {added_tanks.solution_value}, added_batteries: {added_batteries.solution_value}, added_solar_power: {added_solar_power.solution_value}, added_wind_power: {added_wind_power.solution_value}' )
        print(f'')

        leaf_profits = []
        print(f'')
        for s in S:
            print(f'Satge 2, Scenario {s}:')
            print(f'Node specific profit: {Profit2[s].solution_value/scenario_probability[s]}')
            print(f'added_electrolysers: {added_electrolysers_2[s].solution_value}, added_tanks: {added_tanks_2[s].solution_value}, added_batteries: {added_batteries_2[s].solution_value}, added_solar_power: {added_solar_power_2[s].solution_value}, added_wind_power: {added_wind_power_2[s].solution_value}' )
            print(f'')
            leaf_profits.append(Profit2[s].solution_value / scenario_probability[s])
        return Profit_HN.solution_value, leaf_profits, tot_electrolysers.solution_value, tot_tanks.solution_value, tot_batteries.solution_value, Cap_pv.solution_value, tot_wind_power.solution_value
    else:
        print(f'did not solve')
        return 0,0,0,0,0,0,0
    
def main_simulation():
    best_combo=[]
    max_profit = float('-inf')
    iteration_counter=0
    start_time = time.time()
    for sup_num_PTH in range(1, len(ElectrolyzerParams)+1):
        for sup_num_BA in range(1, len(BatteryParams)+1):
            for sup_num_HT in range(1, len(HydrogenTankParams)+1):
                iteration_counter+=1
                print(f'Starting iteration: {iteration_counter}')
                print(f'*********************************************************************************************************')
                stages = 2  # Total number of stages you have
                initial_conditions = {
                    'electrolysers': 0,
                    'tanks': 0,
                    'batteries': 0,
                    'solar_power': 1500,
                    'wind_power': 1
                }
                all_Profits_2 = []
                all_Profits_3 = []
                # First solve for stage 1
                stage_1_profit, node_profits, stage_1_electrolysers, stage_1_tanks, stage_1_batteries, stage_1_solar_power, stage_1_wind_power = solve_node(sup_num_PTH,sup_num_HT,sup_num_BA, 1,1, 1, 2, 0, initial_conditions['electrolysers'],initial_conditions['tanks'], initial_conditions['batteries'], initial_conditions['solar_power'], initial_conditions['wind_power'])
                print(f'stage_1_node_{0}_electrolysers: {stage_1_electrolysers} , stage_1_node_{0}_tanks: {stage_1_tanks} , stage_1_node_{0}_batteries: {stage_1_batteries} , stage_1_node_{0}_solar_power: {stage_1_solar_power} , stage_1_node_{0}_wind_power: {stage_1_wind_power}')
                print(f'')
                # Assume stage 2 has multiple nodes; iterate over them
                stage_2_nodes = range(1, 3)
                stage_3_nodes = range(1, 3)
                stage_3_nodes_per_stage_2 = {
                    1: 2,  # Node 1 of stage 2 leads to nodes 1 and 2 of stage 3
                    2: 2,  # Node 2 of stage 2 leads to nodes 3 and 4 of stage 3    # Node 3 of stage 2 leads to node 5 of stage 3
                }

                stage_4_nodes_per_stage_3 = {
                    1: 2,  # Node 1 of stage 2 leads to nodes 1 and 2 of stage 3
                    2: 2,  # Node 2 of stage 2 leads to nodes 3 and 4 of stage 3
                    3: 2,  
                    4: 2,
                    5: 2,
                    6: 2,
                    7: 2,
                    8: 2     # Node 3 of stage 2 leads to node 5 of stage 3
                }
                leaf_profit={}
                for node in stage_2_nodes:
                    # Solve for each node in stage 2
                    stage_2_profit, node_profits, stage_2_electrolysers, stage_2_tanks, stage_2_batteries, stage_2_solar_power, stage_2_wind_power=solve_node(sup_num_PTH,sup_num_HT,sup_num_BA,1,1, 2, stage_3_nodes_per_stage_2[node], node, stage_1_electrolysers, stage_1_tanks, stage_1_batteries, stage_1_solar_power, stage_1_wind_power)
                    print(f'stage_2_node_{node}_electrolysers: {stage_2_electrolysers} , stage_2_node_{node}_tanks: {stage_2_tanks} , stage_2_node_{node}_batteries: {stage_2_batteries} , stage_2_node_{node}_solar_power: {stage_2_solar_power} , stage_2_node_{node}_wind_power: {stage_2_wind_power}')
                    print(f'')
                    all_Profits_2.append(stage_2_profit)
                    leaf_profit[node]=node_profits
    

                print(f'Summary:')
                print(f'****************************************************************************************')
                print(f'stage_1_profit:{stage_1_profit}')
                scenario_number=0
                total_profit=0
                for node in stage_2_nodes:
                    print(f'Profit at node {node}: {all_Profits_2[node-1]}')
                    print(f'Node profits: {leaf_profit[node]}')
                    for i in range(len(leaf_profit[node])):
                        scenario_number+=1
                        scenario_profit=stage_1_profit+all_Profits_2[node-1]+leaf_profit[node][i]
                        print(f'Scenario {scenario_number} profit: {scenario_profit}')
                        total_profit+=scenario_profit
                total_model_profit=total_profit/scenario_number
                print(f'Total model profit {total_model_profit}')
                if total_model_profit>max_profit:
                    max_profit=total_model_profit
                    best_combo = (sup_num_PTH, sup_num_BA, sup_num_HT)
                    print(f'improvement found with: {best_combo}')
                else:
                    print(f'No improvement found')
                end_time = time.time()  # Record end time
                print(f"End of iteration {iteration_counter}")
                print(f"**********************************************************************************")
    print(f'Best Combo is: {best_combo} with a total profit of: {max_profit}')
    print(f"Simulation took {end_time - start_time:.2f} seconds to complete.")   
              
if __name__ == "__main__":
    main_simulation()
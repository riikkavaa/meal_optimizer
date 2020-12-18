#!/usr/bin/env python
# coding: utf-8

import sys
print(sys.version)

import pandas as pd
import numpy as np

from io import StringIO
import requests
import json

import pulp as pulp
#pulp.pulpTestAll()

def read_data():
    """
    Reading data from Finelli's webpage.
    Page apparently allows requests only by web browsers, so lets pretend to be one.
    Output:
    Original data saved into a pandas Dataframe
    """
    
    data_url="https://fineli.fi/fineli/en/elintarvikkeet/resultset.csv"

    header = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.2661.75 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest"
    }

    try:
        s=requests.get(data_url, headers=header).text
        data=pd.read_csv(StringIO(s), sep=';')
        return data

    except:
        return None



def read_constraints():

    """
    Loading numerical values to constraints. Energy is converted to kJ.
    """
    
    energy_limit=2000* 4.184
    
    constraint_values={
        'energy_limit_kJ':energy_limit,
        'fibre_lower_limit':20,
        'individual_component_upper_limit':5,
        'fat_target':0.2,
        'protein_target':0.3,
        'carb_target':0.5,
        'fat_limit':0.2*energy_limit,
        'protein_limit':0.3*energy_limit,
        'carb_limit':0.5*energy_limit,
        'food_group_limit':3
    }
    return constraint_values


def preprocess_data(data, energy_cutoff=10):
    """
    Preprocess data frame:
    1. Select only the columns needed
    2. Transform numeric columns to numeric values, 
       fill '< something' values with 0.
    3. Set energy minimum limit. Zero energy foods 
       somehow disturb the food groups.
    4. Amounts of carbs, proteins and fats are given in mass density. 
       Transform these into energy density.
    
    Input:
    data: Pandas dataframe containing data of the food items
    energy_cutoff: remove the foods with very low energy density -> 
    not need to eat 500 g salt.
    
    Output:
    
    Pandas dataframe.
    New columns added: ['carb, energy','protein, energy','fat, energy']
    
    """
    
    cols_selected=[ 'id', 'name', 'energy,calculated (kJ)', 
                    'carbohydrate, available (g)',
                    'fat, total (g)', 'protein, total (g)',
                    'fibre, total (g)',  'sugars, total (g)',   ]
     
    data=data[cols_selected].copy()
    
    data.loc[:,'id']=pd.to_numeric(data['id'], errors='coerse')
    data=data[data['id'].notna()].copy()
    
    data.loc[:,'name']=data['name'].astype(str)
        
    data.loc[:,'energy,calculated (kJ)']=pd.to_numeric(data['energy,calculated (kJ)'], 
                                                        errors='coerse').fillna(0)
    data.loc[:,'carbohydrate, available (g)']=pd.to_numeric(data['carbohydrate, available (g)'], 
                                                        errors='coerse').fillna(0)
    data.loc[:,'fat, total (g)']=pd.to_numeric(data['fat, total (g)'], 
                                                        errors='coerse').fillna(0)
    data.loc[:,'protein, total (g)']=pd.to_numeric(data['protein, total (g)'], 
                                                        errors='coerse').fillna(0)
    data.loc[:,'sugars, total (g)']=pd.to_numeric(data['sugars, total (g)'], 
                                                        errors='coerse').fillna(0)
    data.loc[:,'fibre, total (g)']=pd.to_numeric(data['fibre, total (g)'], 
                                                        errors='coerse').fillna(0)
    
    data=data[data['energy,calculated (kJ)']>energy_cutoff]
    
    # Amount of energy (kJ) per gram for each macronutrients. Data from wikipedia:
    # https://en.wikipedia.org/wiki/Food_energy
    energy_consts={'carbohydrate':17, 'protein':17, 'fat':37}
    data.loc[:,'carb, energy']=energy_consts['carbohydrate']*data['carbohydrate, available (g)']
    data.loc[:,'protein, energy']=energy_consts['protein']*data['protein, total (g)']
    data.loc[:,'fat, energy']=energy_consts['fat']*data['fat, total (g)']

    #calc_energy_diff=data['energy,calculated (kJ)']-data[['carb, energy', 'protein, energy', 'fat, energy']].sum(axis=0)
    
    return data

def add_groups(data):
    """
    Two alternatives of first iteration food groups are created
    "first_word" uses the first word
    "First_part" uses the first string before the first comma
    
    
    Input data in pandas dataframe after preprocessing
    Output Dataframe with two new columns ['first word','first part'] 
    """
    
    data['first_word']=data['name'].str.lower().str.replace(',', ' ')\
                                   .str.split(' ').apply(lambda x: x[0])

    data['first_part']=data['name'].str.lower().str.split(',')\
                                   .apply(lambda x: x[0]).str.replace(' ','_')
    
    return data

    


def meal_optimizer(data, food_group_column, c_values, verbose=1):
    
    
    # Create a list of the food items
    food_items = list(data['id'])
    
    # List of food groups
    food_groups=data[food_group_column].unique()

    # For sugar, total energy, carbs, fats, proteins and fibre:
    # create a dicts of the properties for all food items
    sugar = dict(zip(food_items,data['sugars, total (g)']))
    energy = dict(zip(food_items,data['energy,calculated (kJ)']))
    fats = dict(zip(food_items,data['fat, energy']))
    carbs = dict(zip(food_items,data['carb, energy']))
    proteins = dict(zip(food_items,data['protein, energy']))
    fibre = dict(zip(food_items,data['fibre, total (g)']))
    
    # assign a food group to each food item
    food_group=dict(zip(food_items, data[food_group_column]))
    
    # define problem
    prob = pulp.LpProblem('Meal Problem',pulp.LpMinimize)

    # define variables to optimize
    # first value of individual foods
    food_vars = pulp.LpVariable.dicts("Food",food_items,
                                      lowBound=0,cat='Continuous')
    # second indicator variable if a certain food group is chosen or not
    food_group_chosen = pulp.LpVariable.dicts("Group",food_groups,
                                              0,1,cat='Integer')

    # main objective function: minimize sugar
    prob += pulp.lpSum([sugar[i]*food_vars[i] for i in food_items])

    #########
    # constraints:
    # Certain values of energy and how it is divided to carbs, fat and protein

    prob += pulp.lpSum([energy[f] * food_vars[f] for f in food_items]) \
                        ==c_values['energy_limit_kJ']
    prob += pulp.lpSum([carbs[f] * food_vars[f] for f in food_items]) \
                        == c_values['carb_limit']
    prob += pulp.lpSum([fats[f] * food_vars[f] for f in food_items]) \
                        == c_values['fat_limit']
    prob += pulp.lpSum([proteins[f] * food_vars[f] for f in food_items]) \
                        == c_values['protein_limit']
    prob += pulp.lpSum([fibre[f] * food_vars[f] for f in food_items]) \
                        >= c_values['fibre_lower_limit']

    # no more than 5 pieces of 100 g portions each food
    for f in food_items:
        prob+=food_vars[f]<=c_values['individual_component_upper_limit']

    # Here the food items and food groups are connected:
    # The first constraint ensures that the foods from chosen food group are chosen.
    # The second one ensures that if the food group is not chosen 
    # then corresponding food are not chosen.
    # Notice that this brings positive (1e-5) value for
    # all food items from selected food group. 
    # Later we filter out the foods where value is below 1.1*1e-5
    for f in food_items:
        prob += food_vars[f]>= food_group_chosen[food_group[f]]*1e-5
        prob += food_vars[f]<= food_group_chosen[food_group[f]]*1e5


    # The last constraint to force at least three food group
    prob += pulp.lpSum([food_group_chosen[fg] for fg in food_groups]) \
                        >=c_values['food_group_limit']

    #########
    # Optimizing the problem
    status=prob.solve()
    print(pulp.LpStatus[status], ' solution found.')

    # status =1 if there the optimal solution could be found. 
    # Then the optimal meal is extracted and returned
    if status==1:

        # Collect chosen food items to a dict called best_meal. 
        # Includes id, name and portion of the food.
        best_meal={}
        ii=0
        for food_v in prob.variables(): 
            if (str.startswith(food_v.name,'Food')) and (food_v.varValue>1.1*1e-5): 
                f_id=int(food_v.name[5:])
                f_name=data.loc[data['id']==int(food_v.name[5:]), 'name'].values[0]
                best_meal[ii]={'id':f_id, 'name':f_name, 'portion':food_v.varValue}
                ii+=1

        # Collect chosen food groups to a set called best_groups. 
        best_group=set()
        for food_group_v in prob.variables(): 
            if (str.startswith(food_group_v.name,'Group')) and (food_group_v.varValue>0):
                best_group.add(food_group_v.name[6:]) 

        # For printing the result in tabular format, make a dataframe of the chosen food items
        food_df=pd.DataFrame.from_dict(data=best_meal,
                                       orient='index', 
                                       columns=['id','name','portion'])

        output=pd.merge(food_df.drop(columns=['name']), data, 
                        how='left', on='id')
        

        
        # Sum values of energies and fibre over all the chosen food items
        total_energy=np.dot( output['energy,calculated (kJ)'],output['portion'])
        carb_energy=np.dot( output['carb, energy'],output['portion'])/total_energy
        protein_energy=np.dot( output['protein, energy'],output['portion'])/total_energy
        fat_energy=np.dot( output['fat, energy'],output['portion'])/total_energy
        tot_fibre=np.dot(output['fibre, total (g)'],output['portion'])
        
        results={'Total sugar':pulp.value(prob.objective),
                 'Total energy':total_energy,
                 'Carb energy': carb_energy,
                 'protein energy': protein_energy,
                 'Fat energy': fat_energy,
                 'Total fibre': tot_fibre,
                }


        if verbose==1:
            # If results are wanted to print into stdout

            print("Total sugar of the meal = ", 
                  '{:3.2f}'.format(pulp.value(prob.objective)),'g')
            print()
            print('Number of food items:', len(best_meal))  
            
            
            print(food_df.sort_values('portion', ascending=False))

            print()
            print('Number of food groups:', len(best_group))
            print(best_group) 

            print()

            print('Total energy of the meal:','{:5.1f}'.format(total_energy), 
                  'kJ (Limit',c_values['energy_limit_kJ'],')')
                                       
            print('Energy from carbs       :','{:3.1f}'.format(carb_energy*100),
                  '%',  '(Limit',c_values['carb_target']*100,')')
                                       
            print('Energy from protein     :','{:3.1f}'.format(protein_energy*100),
                  '%',  '(Limit',c_values['protein_target']*100,')')
                                       
            print('Energy from fats        :','{:3.1f}'.format(fat_energy*100),
                  '%',  '(Limit',c_values['fat_target']*100,')')
                                       
            print('Total fibre of the meal :','{:3.1f}'.format(tot_fibre),  
                  'g (Limit more than',c_values['fibre_lower_limit'],')')

        return best_meal, best_group, results


    else: # no optimal solutions 
        return None

    


#####################

if __name__ == "__main__":

    constraint_values=read_constraints()

    # reading data, if result is None exit program
    data=read_data()
    if data is None:
        sys.exit("Error: Not able to get datafile.")

    data=preprocess_data(data)
   
    # select a way to define the food groups: either `first_word` or `first_part`
    data=add_groups(data)
    food_group_name='first_part'

    # collect the meals in a dict
    meals={}

    # best_group refers the food groups that were used in the previous day
    best_group=set()

    # For each day, a set of food items is selected,
    # and and optimal meal within these food items is found. 
    # For the first day, all data is included. 
    # For rest of the days, the food items that belong to the previous day's 
    # food groups are removed. 
    for day in range(7):
        print('*'*80)
        print('Day',day)

        new_data=data[~data[food_group_name].isin(list(best_group))]
        try:
            best_meal, best_group, results=meal_optimizer(new_data, 
                        food_group_name, constraint_values, verbose=1)
            meals['day'+str(day)]=best_meal
        except:
            sys.exit('Error: No optimal solution found')
        

    # write resulting meals to file in json format
    with open('/results/results.json', 'w') as outfile:  
        json.dump(meals, outfile, indent=4)




 
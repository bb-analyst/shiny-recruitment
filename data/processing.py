import pandas as pd

def filter_bq_player_data(df,game_types,teams=None,players=None,positions=None,stats=None):
    
    #filter dataframe
    if "Finals" not in game_types:
        df = df[~df["roundName"].str.contains("final", case=False, na=False)]
    if "Regular" not in game_types:
        df = df[df["roundName"].str.contains("final", case=False, na=False)]

    if teams:
        df = df[df["teamId"].isin(teams)]
    if players:
        df = df[df["playerId"].isin(players)]
    if positions:
        df = df[df["playerPosition"].isin(positions)]
    if stats:
        df = df[stats]

    return df.query("mins > 0").sort_values(by=['playerName','roundId'])

def summarise_filtered_data(df,summary_type,min_games,separate_positions,stats,flat_dict):
    
    
    if summary_type == 'Individual Games':
        index_cols = ['playerName','roundName','teamAbbr','playerPositionAbbrev']
        df = df[index_cols + stats]
        df = df.rename(columns=flat_dict)
        return df
    else:
        if separate_positions:
            group_cols = ['playerName','playerPositionAbbrev']
        else:
            group_cols = ['playerName']
        
        if summary_type == 'Game Average':
            agg_func = 'mean'
        if summary_type == 'Game Totals':
            # agg_func = 'sum'
            mean_stats = ['effectiveTacklePercentage']
            agg_func = {stat: 'mean' if stat in mean_stats else 'sum' for stat in stats}
        
        #get most recent team for each player
        teams = df.groupby(group_cols)['teamAbbr'].last() 
        #get match counts for each player
        matches = df.groupby(group_cols).size()

        #summarise df
        df = df.groupby(group_cols)[stats].agg(agg_func).round(2)

        #insert matches
        df.insert(loc=0, column='teamAbbr', value=teams)
        df.insert(loc=1, column='MAT', value=matches)
        
        #reset index
        df = df.reset_index()

        #rename columns to shorthand
        df = df.rename(columns=flat_dict)

        return df

def leaderboard_df(df,stat,summary_type,min_games,top_n):
    if summary_type == 'Game Average':
        agg_func = {stat:'mean','roundId':'count'}
    if summary_type == 'Game Totals':
        agg_func = {stat:'sum','roundId':'count'}
    if summary_type == 'Game Best':
        agg_func = {stat:'max','roundId':'count'}
    
    df = df.groupby('playerName').agg(agg_func).rename(columns={stat:'Value','roundId':'MAT'}).query(f'MAT >= {min_games}').sort_values(by='Value',ascending=False).nlargest(top_n,'Value',keep='all').round(2).reset_index().drop(columns=['MAT'])
    return df
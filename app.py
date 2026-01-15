from shiny import App, ui, render, reactive
from shinyswatch import theme
import pandas as pd
import plotly.express as px
import os
import json
from google.oauth2 import service_account
from google.cloud import bigquery
from dotenv import load_dotenv
from pathlib import Path
from data import queries, processing

# #Authenticate
# key_path = Path(__file__).parent / "recruitment_bq.json"
# credentials = service_account.Credentials.from_service_account_file(str(key_path))
# client = bigquery.Client(credentials=credentials)
# client = queries.get_client()

# Load environment variables from .env file
load_dotenv()
# Authenticate
# Use individual environment variables
service_account_info = {
    "type": "service_account",
    "project_id": "rugbaleeg",
    "private_key_id": os.getenv("GCP_PRIVATE_KEY_ID"),
    "private_key": os.getenv("GCP_PRIVATE_KEY").replace('\\n', '\n'),  # Fix newlines
    "client_email": os.getenv("GCP_CLIENT_EMAIL"),
    "client_id": os.getenv("GCP_CLIENT_ID"),
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/shiny-recruitment%40rugbaleeg.iam.gserviceaccount.com",
    "universe_domain": "googleapis.com"
}
credentials = service_account.Credentials.from_service_account_info(service_account_info)
client = bigquery.Client(credentials=credentials)


#Constants
# comps_dict = {
#     'nrl': 111,
#     'nswcup': 113,
#     'qcup': 114,
#     'origin': 116,
#     'superleague': 121,
#     'haroldmatthews': 143,
#     'sgball': 144,
#     'cyrilconnell': 154,
#     'malmeninga': 155,
#     'jerseyflegg': 159,
#     'nrlw': 161
# }
#Constants
broncos_maroon = '#540c2b'
broncos_gold = '#f0a91f'



comps_dict = {
    111:'nrl',
    113:'nswcup',
    114:'qcup',
    116:'origin',
    121:'superleague',
    143:'haroldmatthews',
    144:'sgball',
    154:'cyrilconnell',
    155:'malmeninga',
    159:'jerseyflegg',
    161:'nrlw'
}

seasons_list = [2023,2024,2025]

summary_list = ['Game Average', 'Game Totals', 'Individual Games']

positions_list = ['Fullback', 'Winger', 'Centre', 'Five-Eighth', 'Halfback',
                  'Hooker','Prop', '2nd Row', 'Lock', 'Interchange']

with open("stats.json", "r") as f:
    stats_dict =json.load(f)

stats_flattened_dict = {k: v for d in stats_dict.values() for k, v in d.items()}

default_stats = ['allRuns','allRunMetres',
                 'tries','tryAssists',
                 'linebreaks','linebreakAssists',
                 'tackleBreaks',
                 'tackles','missedTackles','ineffectiveTackles','effectiveTacklePercentage',
                 'errors','penalties']

leaderboard_defaults = {
    'WG': ['tries','allRuns','tackles'],
    'CT': ['tries','allRuns','tackles'],
    'FB': ['tries','allRuns','tackles'],
    'FE': ['tries','allRuns','tackles'],
    'HB': ['tries','allRuns','tackles'],
    'HK': ['tries','allRuns','tackles'],
    '2R': ['tries','allRuns','tackles'],
    'PR': ['tries','allRuns','tackles'],
    'LK': ['tries','allRuns','tackles'],
    'INT': ['tries','allRuns','tackles']
}

def create_position_tabs():
    tabs = []
    for position_abbrev, default_stats in leaderboard_defaults.items():
        tab = ui.nav_panel(
            position_abbrev,  # Display full name
            ui.input_selectize(
                f"stats_{position_abbrev}",  # Use code as ID
                None,
                choices={category:stats_dict[category] for category in ['Attack','Defence','Discipline','Kicking']},
                selected=default_stats,
                multiple=True,
                width="100%"
            ),
            ui.output_ui(f"cards_{position_abbrev}")
        )
        tabs.append(tab)
    return tabs

#UI

#Add pages

#Home will be about games completed/data collected
#Player Table
#Leaderboards
#Analyzer file downloader + video player

home_page = ui.nav_panel(
    "Home",
    ui.h2("Welcome to the Recruitment Dashboard"),
    ui.p("Select a page from the navigation above. See the up to date data below."),
    ui.output_ui("fixture_cards")
)

table_page = ui.nav_panel(
    "Player Table",
    ui.h2("Player Statistics Table"),
    ui.p("Use the filters on the left to customise the player statistics table. You can sort by a column by clicking the header."),
    ui.layout_sidebar(
        ui.sidebar(
            ui.h4("Filters"),
            # ui.input_selectize("competition",
            #                 "Comp:",
            #                 choices={str(i):j for i,j in comps_dict.items()},
            #                 selected='111',
            #                 multiple=False),
            # ui.input_checkbox("competition_separate",
            #                 "Separate Comps", 
            #                 value=True),
            # ui.input_selectize("season",
            #                 "Season:",
            #                 choices=[str(i) for i in seasons_list],
            #                 selected='2025',
            #                 multiple=False),
            # ui.input_checkbox("season_separate",
            #                 "Separate Seasons", 
            #                 value=True),
            ui.hr(style="margin-top: 0px; margin-bottom: 0px;"),
            ui.input_selectize("summary",
                            "Summary Type:",
                            choices=summary_list,
                            selected='Game Average'),
            ui.input_slider("min_games", 
                            "Minimum Games:", 
                            1, 10, 1, step=1),
            ui.input_checkbox_group("game_types",
                                    None, 
                                    choices=['Regular', 'Finals'],
                                    selected=['Regular'],
                                    inline=True),
            ui.hr(style="margin-top: 0px; margin-bottom: 0px;"),
            ui.input_selectize("team",
                            "Teams:",
                            choices=[],
                            selected=[],
                            multiple=True),
            ui.input_selectize("player",
                            "Players:",
                            choices=[],
                            selected=[],
                            multiple=True),
            ui.input_selectize("position",
                            "Positions:",
                            choices=positions_list,
                            selected=[],
                            multiple=True),
            ui.input_checkbox("position_separate",
                            "Separate Positions", 
                            value=False),
            ui.hr(style="margin-top: 0px; margin-bottom: 0px;"),
            ui.input_selectize("stats",
                            "Stats:",
                            choices={category:stats_dict[category] for category in ['Attack','Defence','Discipline','Kicking']},
                            selected=default_stats,
                            multiple=True)
        ),
        ui.output_data_frame("player_table")
    )
)

leaderboard_page = ui.nav_panel(
    "Leaderboards",
    ui.h2("Leaderboards"),
    ui.p("See top players in various statistical categories."),
    ui.layout_columns(
        ui.input_selectize("leaderboard_summary",
            "Summary Type:",
            choices=['Game Average', 'Game Totals','Game Best'],
            selected='Game Average'),
        ui.input_slider("leaderboard_min_games", 
            "Minimum Games:", 
            value=5,
            min=1,
            max=10,
            step=1),
        ui.input_slider("leaderboard_top_n",
            "Top N Players:",
            value=5,
            min=1,
            max=10,
            step=1),
        col_widths=[4, 4, 4],  # Each takes up 1/3 of the width
        style="margin-bottom: 1rem;max-height: 50px;" 
    ),
    ui.navset_tab(
        *create_position_tabs(),
    )
)

app_ui = ui.page_navbar(
    home_page,
    table_page,
    leaderboard_page,
    ui.nav_spacer(),
    ui.nav_control(
        ui.div(
            ui.input_selectize("competition",
                None,
                choices={str(i):j for i,j in comps_dict.items()},
                selected='111',
                multiple=False,
                width='100px'
            ),
        )        
    ),
    ui.nav_control(
        ui.div(
            ui.input_selectize("season",
                None,
                choices=[str(i) for i in seasons_list],
                selected='2025',
                multiple=False,
                width='100px'
            ),
        )
    ),
    title="Recruitment Dashboard",
    fillable=True,
    theme=theme.flatly(),
    id="navbar",
    header=ui.tags.link(href="css.css", rel="stylesheet")
)

#Server
def server(input, output, session):

    #Fetch Fixture Data from BigQuery
    @reactive.calc
    def fixture_data():
        reactive.invalidate_later(7200) 
        df = queries.fetch_bq_latest_fixtures(client)
        return df.sort_values(by=['competitionName','roundId','gameNumber'])

    @render.ui
    def fixture_cards():
        df = fixture_data()
        if len(df) == 0 or df is None:
            return ui.p("No fixtures available.")
        
        grouped = df.groupby(['competitionId','competitionName','roundName'])

        cards = []
        for (comp_id,comp_name,round_name), group_df in grouped:
            #Create table
            table_df = group_df[['gameNumber','game','gameStateName']].copy()
            
            # Replace gameStateId with icons
            table_df['gameStateName'] = table_df['gameStateName'].apply(lambda x: '✅' if x == 'Final' else '❌')
            
            # Convert to HTML table with Bootstrap styling
            table_html = table_df.to_html(
                index=False,
                header=False, 
                classes="table table-hover table-sm fixture-columns",
                border=0
            )
            
            card = ui.card(
                ui.card_header(f"{comp_name} - {round_name}"),
                ui.HTML(table_html)
            )
            cards.append(card)
        
        return ui.div(*cards)


    
    #Fetch data from BigQuery when comp or season changes
    @reactive.calc
    def bigquery_data():
        reactive.invalidate_later(86400)
        comp = int(input.competition())
        season = int(input.season())
        if not comp or not season:
            return pd.DataFrame()
        stats = [k for c in stats_dict.keys() for k in stats_dict[c]]
        df = queries.fetch_bq_player_data(client, comp, season, stats)
        return df
    
    #Update team choices when BigQuery data changes
    @reactive.effect
    def update_team_choices():
        df = bigquery_data()
        teams = (
            df[["teamId", "teamNickName"]]
            .drop_duplicates()
            .sort_values("teamNickName")
            .set_index("teamId")["teamNickName"]
            .astype(str)  # ensure values are strings (optional)
            .to_dict()
        )
        teams = {str(k): v for k, v in teams.items()}
        ui.update_select("team", choices=teams)

    #Update player choices when BigQuery data changes and team selection changes
    @reactive.effect
    def update_player_choices():
        df = bigquery_data()
        selected_teams = input.team()
        if selected_teams:
            df = df[df["teamId"].astype(str).isin(selected_teams)]

        players = (
            df[["playerId", "playerName"]]
            .drop_duplicates()
            .sort_values("playerName") 
            .set_index("playerId")["playerName"]
            .astype(str)  # ensure values are strings (optional)
            .to_dict()
        )
        players = {str(k): v for k, v in players.items()}
        ui.update_select("player", choices=players)

    #Filter bigquery data based on inputs
    @reactive.calc
    def filtered_data():
        df = bigquery_data()

        #Get filter inputs
        game_types = input.game_types()
        teams = input.team()
        teams = [int(t) for t in teams] if teams else None
        players = input.player()
        players = [int(p) for p in players] if players else None
        positions = input.position()
        stats = list(input.stats())
        stats = list(stats_dict['Always'].keys()) + stats

        #Filter
        filtered_df = processing.filter_bq_player_data(
            df,
            game_types,
            teams,
            players,
            positions,
            stats
        )

        return filtered_df
    
    #Summarise filtered data
    @reactive.calc
    def summarised_data():
        df = filtered_data()
        summary_type = input.summary()
        min_games = input.min_games()
        separate_positions = input.position_separate()
        stats = list(input.stats())
        stats = ['mins'] + stats
        summarised_df = processing.summarise_filtered_data(
            df,
            summary_type,
            min_games,
            separate_positions,
            stats,
            stats_flattened_dict
        )

        return summarised_df
    
    @output
    @render.data_frame
    def player_table():
        df = summarised_data()
        return render.DataGrid(
            df,
        )

    # Helper function to create leaderboard cards
    def create_leaderboard_cards(position_abbrev):
        stats = input[f"stats_{position_abbrev}"]()
        
        
        if not stats:
            return ui.p("No stats selected.")
        
        # Get summary type
        summary_type = input.leaderboard_summary()
        
        cards = []
        for stat in stats:
            
            output_id = f"grid_{position_abbrev}_{stat}"
            
            # Get the display name from stats_flattened_dict
            stat_display_name = stats_flattened_dict.get(stat, stat)

            card = ui.div(
                {"class": "col-12 col-sm-6 col-md-4 col-lg-3"},
                ui.card(
                    ui.card_header(f"{stat_display_name} - {summary_type}"),
                    ui.output_data_frame(output_id),
                    class_="leaderboard-grid-card"
                )
            )
            cards.append(card)

            # Create renderer with @output decorator
            def make_renderer(pos_abbrev, stat_name, out_id):
                @output(id=out_id)
                @render.data_frame
                def _():
                    df = filtered_data()
                    
                    # Use a local variable for the query
                    position = pos_abbrev
                    df = df[df['playerPositionAbbrev'] == position]
                    
                    summary_type = input.leaderboard_summary()
                    min_games = input.leaderboard_min_games()
                    top_n = input.leaderboard_top_n()

                    leaderboard = processing.leaderboard_df(
                        df,
                        stat_name,
                        summary_type,
                        min_games,
                        top_n
                    )
                    
                    return render.DataGrid(
                        leaderboard,
                        width="100%",
                        height="auto",
                        filters=False,
                        summary=False
                    )
                return _
            
            # Call the renderer to register it
            make_renderer(position_abbrev, stat, output_id)
        
        return ui.div({"class": "row"}, *cards)

    # Now manually create each output
    @output
    @render.ui
    def cards_WG():
        return create_leaderboard_cards('WG')
    
    @output
    @render.ui
    def cards_CT():
        return create_leaderboard_cards('CT')
    
    @output
    @render.ui
    def cards_FB():
        return create_leaderboard_cards('FB')
    
    @output
    @render.ui
    def cards_FE():
        return create_leaderboard_cards('FE')
    
    @output
    @render.ui
    def cards_HB():
        return create_leaderboard_cards('HB')
    
    @output
    @render.ui
    def cards_HK():
        return create_leaderboard_cards('HK')
    
    @output
    @render.ui
    def cards_2R():
        return create_leaderboard_cards('2R')
    
    @output
    @render.ui
    def cards_PR():
        return create_leaderboard_cards('PR')
    
    @output
    @render.ui
    def cards_LK():
        return create_leaderboard_cards('LK')
    
    @output
    @render.ui
    def cards_INT():
        return create_leaderboard_cards('INT')


app_dir = Path(__file__).parent
app = App(app_ui, server, static_assets=app_dir / "www")
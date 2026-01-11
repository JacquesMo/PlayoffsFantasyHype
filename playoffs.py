import streamlit as st
import requests
import pandas as pd
import json
import os
from datetime import datetime

# --- CONFIGURATION ---
# Your RapidAPI Key
API_KEY = "aef7c53587msh8625f65e7e1022cp12a5ccjsn374e22013162"

HEADERS = {
    "X-RapidAPI-Key": API_KEY,
    "X-RapidAPI-Host": "tank01-nfl-live-in-game-real-time-statistics-nfl.p.rapidapi.com"
}

# Local storage for persistence across weeks
DB_FILE = "playoff_data.json"

# Playoff Schedule Rounds
PLAYOFF_ROUNDS = ["Wild Card", "Divisional", "Conference Championship", "Super Bowl"]

# --- ELIMINATED TEAMS ---
# ADMIN: Add the 2 or 3 letter abbreviation of eliminated teams here to highlight them in red.
# Example: ["MIA", "NYG", "CLE"]
ELIMINATED_TEAMS = [] 

# --- NAME MAPPER ---
# Ensuring nicknames match official API LongNames
NAME_MAP = {
    "CMC": "Christian McCaffrey",
    "Tae": "Davante Adams",
    "Rome": "Rome Odunze",
    "Njigba": "Jaxon Smith-Njigba",
    "Corum": "Blake Corum",
    "Charb": "Zach Charbonnet",
    "Kenneth": "Kenneth Walker III",
    "Shakir": "Khalil Shakir",
    "Diggs": "Stefon Diggs",
    "Nico": "Nico Collins",
    "Puka": "Puka Nacua", 
    "'Drake Maye'": "Drake Maye",
    "Kyren": "Kyren Williams"
}

# --- YOUR TEAMS ---
TEAMS = {
    "Max": ["Trevor Lawrence", "TreVeyon Henderson", "Puka", "Nico", "Christian Watson", "Parker Washington"],
    "Mash": ["Matthew Stafford", "James Cook", "A.J. Brown", "Rome", "Woody Marks", "Blake Corum"],
    "Relph": ["Sam Darnold", "Travis Etienne Jr.", "Njigba", "Courtland Sutton", "Dallas Goedert", "Omarion Hampton"],
    "Ovi": ["Caleb Williams", "CMC", "Tae", "Diggs", "Rhamondre Stevenson", "Luther Burden III"],
    "Matalon": ["'Drake Maye'", "Kyren", "DeVonta Smith", "Jauan Jennings", "RJ Harvey", "Hunter Henry"],
    "Jacq/MG3": ["Josh Allen", "Saquon Barkley", "Shakir", "DK Metcalf", "Kenneth", "Charb"]
}

# --- DATABASE LOGIC ---
def load_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            try:
                data = json.load(f)
                
                # Basic validation/migration: ensure data is in new dict format if it was old floats
                first_manager = list(TEAMS.keys())[0]
                if first_manager in data:
                    first_round = PLAYOFF_ROUNDS[0]
                    # Check if the value is a float (old format) or dict (new format)
                    val = data[first_manager].get(first_round)
                    if isinstance(val, (float, int)):
                        new_data = {}
                        for mgr, rounds in data.items():
                            new_data[mgr] = {}
                            for r, value in rounds.items():
                                new_data[mgr][r] = {"Total": value} if isinstance(value, (int, float)) else value
                        data = new_data
                
                # Ensure keys exist for new features
                if "WeeklyStats" not in data:
                    data["WeeklyStats"] = {}
                if "PlayerTeams" not in data:
                    data["PlayerTeams"] = {}
                    
                return data
            except json.JSONDecodeError:
                pass # Fallback to initial data if file is corrupt

    initial_data = {
        manager: {round_name: {"Total": 0.0} for round_name in PLAYOFF_ROUNDS} 
        for manager in TEAMS
    }
    initial_data["WeeklyStats"] = {}
    initial_data["PlayerTeams"] = {} # Store Player -> NFL Team mapping
    return initial_data

def save_data(data):
    with open(DB_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# --- API FETCHING ---
def fetch_live_playoff_stats():
    # Initialize dictionary to hold stats for ALL rounds
    stats_by_round = {r: {} for r in PLAYOFF_ROUNDS}
    
    # Initialize dictionary to hold detailed stats segregated by ROUND
    weekly_detailed_stats = {r: {} for r in PLAYOFF_ROUNDS}

    # Store Player -> NFL Team mapping (e.g. {"Josh Allen": "BUF"})
    player_teams_map = {}

    week_map = {
        1: "Wild Card",
        2: "Divisional",
        3: "Conference Championship",
        4: "Super Bowl"
    }

    url_games = "https://tank01-nfl-live-in-game-real-time-statistics-nfl.p.rapidapi.com/getNFLGamesForWeek"
    url_box = "https://tank01-nfl-live-in-game-real-time-statistics-nfl.p.rapidapi.com/getNFLBoxScore"

    # Loop through all 4 playoff weeks
    for week_num, round_name in week_map.items():
        params_games = {"week": str(week_num), "seasonType": "post", "season": "2025"}
        
        try:
            # Fetch Games for this specific playoff week
            resp = requests.get(url_games, headers=HEADERS, params=params_games).json()
            games = resp.get('body', [])
            
            if not games:
                continue # No games for this round yet

            # Fetch stats for each game in this week
            for game in games:
                game_id = game.get('gameID')
                
                # Fetch Box Score
                params_box = {"gameID": game_id, "fantasyPoints": "true"}
                box_data = requests.get(url_box, headers=HEADERS, params=params_box).json()
                
                p_stats = box_data.get('body', {}).get('playerStats', {})
                for pid, info in p_stats.items():
                    name = info.get('longName')
                    team_abbr = info.get('team', '') # Capture NFL Team
                    
                    if name and team_abbr:
                        player_teams_map[name] = team_abbr

                    # --- EXTRACT RAW STATS SAFELY ---
                    passing = info.get('Passing', {})
                    rushing = info.get('Rushing', {})
                    receiving = info.get('Receiving', {})
                    
                    # Yards
                    p_yds = int(passing.get('passYds', 0) or 0)
                    r_yds = int(rushing.get('rushYds', 0) or 0)
                    rec_yds = int(receiving.get('recYds', 0) or 0)
                    
                    # TDs
                    p_td = int(passing.get('passTD', 0) or 0)
                    r_td = int(rushing.get('rushTD', 0) or 0)
                    rec_td = int(receiving.get('recTD', 0) or 0)

                    # Receptions
                    rec_count = int(receiving.get('receptions', 0) or 0)
                    
                    # Turnovers
                    ints = int(passing.get('int', 0) or 0)
                    fumbles = int(info.get('fumblesLost', 0) or 0)
                    
                    # 2Pt (Approximate based on common keys)
                    tp_pass = int(passing.get('twoPtPass', 0) or 0)
                    tp_rush = int(rushing.get('twoPtRush', 0) or 0)
                    tp_rec = int(receiving.get('twoPtRec', 0) or 0)

                    # --- MANUAL PPR CALCULATION ---
                    ppr_score = (
                        (p_yds * 0.04) +      # Passing Yards
                        (p_td * 4) +          # Passing TDs
                        (r_yds * 0.1) +       # Rushing Yards
                        (r_td * 6) +          # Rushing TDs
                        (rec_yds * 0.1) +     # Receiving Yards
                        (rec_td * 6) +        # Receiving TDs
                        (rec_count * 1) +     # Receptions
                        (tp_pass * 2) +       # 2Pt Pass
                        (tp_rush * 2) +       # 2Pt Rush
                        (tp_rec * 2) -        # 2Pt Rec
                        (ints * 2) -          # Interceptions (-2)
                        (fumbles * 2)         # Fumbles Lost (-2)
                    )
                    
                    ppr_score = round(ppr_score, 2)
                    
                    # Add to the specific round bucket
                    stats_by_round[round_name][name] = ppr_score
                    
                    # --- AGGREGATE DETAILED STATS FOR THIS ROUND ---
                    if name not in weekly_detailed_stats[round_name]:
                        weekly_detailed_stats[round_name][name] = {
                            "Passing Yards": 0,
                            "Rush/Rec Yards": 0,
                            "Passing TD": 0,
                            "Rush/Rec TD": 0,
                            "Receptions": 0,
                            "Fumble/Pick": 0,
                            "2Pt Conv": 0,
                            "PPR": 0.0
                        }
                    
                    # Update totals
                    stats_ref = weekly_detailed_stats[round_name][name]
                    stats_ref["Passing Yards"] += p_yds
                    stats_ref["Rush/Rec Yards"] += (r_yds + rec_yds)
                    stats_ref["Passing TD"] += p_td
                    stats_ref["Rush/Rec TD"] += (r_td + rec_td)
                    stats_ref["Receptions"] += rec_count
                    stats_ref["Fumble/Pick"] += (ints + fumbles)
                    stats_ref["2Pt Conv"] += (tp_pass + tp_rush + tp_rec)
                    stats_ref["PPR"] += ppr_score

        except Exception as e:
            st.error(f"Error fetching data for {round_name}: {e}")
            
    return stats_by_round, weekly_detailed_stats, player_teams_map

# --- STYLING HELPERS ---
def style_eliminated_rows(row, player_teams_db):
    """
    Pandas styling function to highlight rows in red if the player's team is eliminated.
    Expects 'Player' to be a column in the row.
    """
    player_name = row.get("Player")
    if not player_name:
        return ['' for _ in row]
    
    # Map back to API name to look up team
    api_name = NAME_MAP.get(player_name, player_name)
    team = player_teams_db.get(api_name)
    
    # Check if team is eliminated
    if team and team in ELIMINATED_TEAMS:
        return ['background-color: #ffcccc; color: #8b0000;' for _ in row]
    return ['' for _ in row]

# --- STREAMLIT UI ---
st.set_page_config(page_title="Playoff Fantasy", layout="wide")
st.title("🏈 Relph League Playoff Fantasy")

# Load existing data
current_db = load_data()

# Sidebar controls
st.sidebar.header("Admin Controls")
st.sidebar.caption("Points are automatically assigned to weeks based on API Week Number (1=WC, 2=Div, 3=Conf, 4=SB).")

# --- RESET BUTTON ---
if st.sidebar.button("⚠️ Reset All Data", help="Clears all saved points and resets to zero."):
    empty_data = {
        manager: {round_name: {"Total": 0.0} for round_name in PLAYOFF_ROUNDS} 
        for manager in TEAMS
    }
    empty_data["WeeklyStats"] = {}
    empty_data["PlayerTeams"] = {}
    save_data(empty_data)
    st.rerun()

st.divider()

if st.button('🔄 Fetch & Save Live Stats'):
    with st.spinner('Checking game status & team affiliations...'):
        live_stats_by_round, weekly_detailed_stats, player_teams_map = fetch_live_playoff_stats()
        
        if live_stats_by_round:
            # 1. Update Scores
            for round_name, player_stats in live_stats_by_round.items():
                if not player_stats: continue

                for manager, roster in TEAMS.items():
                    team_round_total = 0
                    round_detail = {} 
                    
                    for player in roster:
                        api_name = NAME_MAP.get(player, player)
                        pts = player_stats.get(api_name, 0.0)
                        team_round_total += pts
                        round_detail[player] = pts
                    
                    round_detail["Total"] = round(team_round_total, 2)
                    current_db[manager][round_name] = round_detail
            
            # 2. Update Detailed Stats
            current_db["WeeklyStats"] = weekly_detailed_stats
            
            # 3. Update Player Teams (Merge with existing to keep history)
            if "PlayerTeams" not in current_db:
                current_db["PlayerTeams"] = {}
            current_db["PlayerTeams"].update(player_teams_map)
            
            save_data(current_db)
            st.success("Stats & Team Status Updated!")
        else:
            st.error("Could not retrieve live stats.")

# --- TABS FOR VIEWING DATA ---
tab1, tab2 = st.tabs(["🏆 Leaderboard & Rosters", "📊 Player Stats"])

with tab1:
    # --- DISPLAY LEADERBOARD ---
    summary_data = {}
    for manager, rounds in current_db.items():
        if manager in ["WeeklyStats", "PlayerStats", "PlayerTeams"]: continue
        
        summary_data[manager] = {}
        for r, details in rounds.items():
            if isinstance(details, dict):
                summary_data[manager][r] = details.get("Total", 0.0)
            else:
                summary_data[manager][r] = details 

    df = pd.DataFrame.from_dict(summary_data, orient='index')
    df['Total'] = df.sum(axis=1)
    df = df.sort_values(by="Total", ascending=False)

    st.subheader("Leaderboard")
    st.dataframe(
        df.style.background_gradient(subset=['Total'], cmap='Greens')
        .format("{:.2f}")
    )

    # --- DETAILED ROSTER BREAKDOWN ---
    st.header("Team Rosters & Weekly Breakdown")
    if ELIMINATED_TEAMS:
        st.caption(f"🟥 Highlighted rows indicate players on eliminated teams: {', '.join(ELIMINATED_TEAMS)}")

    for manager, roster in TEAMS.items():
        with st.expander(f"{manager}'s Team"):
            team_breakdown = []
            for player in roster:
                player_row = {"Player": player}
                player_total = 0
                
                for r in PLAYOFF_ROUNDS:
                    round_data = current_db.get(manager, {}).get(r, {})
                    if isinstance(round_data, dict):
                        score = round_data.get(player, 0.0)
                    else:
                        score = 0.0 
                    
                    player_row[r] = score
                    player_total += score
                
                player_row["Total"] = player_total
                team_breakdown.append(player_row)
            
            team_df = pd.DataFrame(team_breakdown)
            
            # Apply Elimination Highlight
            formatted_df = team_df.style.format({r: "{:.2f}" for r in PLAYOFF_ROUNDS + ["Total"]}) \
                .background_gradient(subset=["Total"], cmap="Blues") \
                .apply(lambda row: style_eliminated_rows(row, current_db.get("PlayerTeams", {})), axis=1)

            st.dataframe(formatted_df)

with tab2:
    st.header("Detailed Player Stats")
    
    # Retrieve stats from DB
    weekly_stats_db = current_db.get("WeeklyStats", {})
    player_teams_db = current_db.get("PlayerTeams", {})
    
    # Dropdown to select view
    view_options = ["All Rounds (Cumulative)"] + PLAYOFF_ROUNDS
    selected_view = st.selectbox("Select Week", view_options)
    
    all_player_stats = []
    
    # Iterate through ALL managers to get their players
    for manager, roster in TEAMS.items():
        for player in roster:
            # Map Roster Name -> API Name
            api_name = NAME_MAP.get(player, player)
            team_abbr = player_teams_db.get(api_name, "")
            
            # Initialize stats for this player
            combined_stats = {
                "Team": team_abbr,
                "Passing Yards": 0, "Rush/Rec Yards": 0, "Passing TD": 0,
                "Rush/Rec TD": 0, "Receptions": 0, "Fumble/Pick": 0, "2Pt Conv": 0,
                "PPR": 0.0
            }
            
            found_data = False
            
            if selected_view == "All Rounds (Cumulative)":
                # Aggregate across all rounds
                for r in PLAYOFF_ROUNDS:
                    round_data = weekly_stats_db.get(r, {}).get(api_name)
                    if round_data:
                        found_data = True
                        for k, v in round_data.items():
                            if k in combined_stats:
                                combined_stats[k] += v
            else:
                # Get specific round data
                round_data = weekly_stats_db.get(selected_view, {}).get(api_name)
                if round_data:
                    found_data = True
                    for k in combined_stats.keys():
                        if k in round_data:
                            combined_stats[k] = round_data[k]
            
            # Create a row
            row = {"Manager": manager, "Player": player}
            row.update(combined_stats)
            all_player_stats.append(row)
            
    if all_player_stats:
        stats_df = pd.DataFrame(all_player_stats)
        stats_df = stats_df.sort_values(by="PPR", ascending=False)
        
        # Apply Styling
        styled_stats_df = stats_df.style.format({
                "Passing Yards": "{:,}",
                "Rush/Rec Yards": "{:,}",
                "Passing TD": "{:,}",
                "Rush/Rec TD": "{:,}",
                "Receptions": "{:,}",
                "Fumble/Pick": "{:,}",
                "2Pt Conv": "{:,}",
                "PPR": "{:.2f}"
            }) \
            .background_gradient(subset=["PPR"], cmap="Oranges") \
            .apply(lambda row: style_eliminated_rows(row, player_teams_db), axis=1)
        
        st.dataframe(styled_stats_df)
    else:
        st.info("No detailed stats available yet. Please click 'Fetch & Save Live Stats'.")
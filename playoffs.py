import streamlit as st
import requests
import pandas as pd
import json
import os
from datetime import datetime

# --- CONFIGURATION ---
# Your RapidAPI Key
# NOTE: In a production app, it is safer to store this in streamlit secrets (.streamlit/secrets.toml)
API_KEY = "aef7c53587msh8625f65e7e1022cp12a5ccjsn374e22013162"

HEADERS = {
    "X-RapidAPI-Key": API_KEY,
    "X-RapidAPI-Host": "tank01-nfl-live-in-game-real-time-statistics-nfl.p.rapidapi.com"
}

# Local storage for persistence across weeks
# NOTE: On hosted Streamlit Community Cloud, local files are ephemeral and reset on reboot.
# For permanent storage, consider using st.session_state with an external database (like Firestore or Google Sheets).
DB_FILE = "playoff_data.json"

# Playoff Schedule Rounds
PLAYOFF_ROUNDS = ["Wild Card", "Divisional", "Conference", "Super Bowl"]

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
    "Diggs": "Stefon Diggs"
}

# --- YOUR TEAMS ---
TEAMS = {
    "Max": ["Trevor Lawrence", "TreVeyon Henderson", "Puka Nacua", "Nico Collins", "Christian Watson", "Parker Washington"],
    "Mash": ["Matthew Stafford", "James Cook", "A.J. Brown", "Rome", "Woody Marks", "Blake Corum"],
    "Relph": ["Sam Darnold", "Travis Etienne Jr.", "Njigba", "Courtland Sutton", "Dallas Goedert", "Omarion Hampton"],
    "Ovi": ["Caleb Williams", "CMC", "Tae", "Diggs", "Rhamondre Stevenson", "Luther Burden III"],
    "Matalon": ["Drake Maye", "Kyren Williams", "DeVonta Smith", "Jauan Jennings", "RJ Harvey", "Hunter Henry"],
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
                        return new_data
                return data
            except json.JSONDecodeError:
                pass # Fallback to initial data if file is corrupt

    initial_data = {
        manager: {round_name: {"Total": 0.0} for round_name in PLAYOFF_ROUNDS} 
        for manager in TEAMS
    }
    return initial_data

def save_data(data):
    with open(DB_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# --- API FETCHING ---
def fetch_live_playoff_stats():
    # Initialize dictionary to hold stats for ALL rounds
    stats_by_round = {r: {} for r in PLAYOFF_ROUNDS}
    
    # Map API weeks to our Round Names
    # Week 1 = Wild Card, Week 2 = Divisional, etc.
    week_map = {
        1: "Wild Card",
        2: "Divisional",
        3: "Conference",
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
                    # Grab PPR points
                    ppr = float(info.get('fantasyPointsDefault', {}).get('PPR', 0))
                    
                    # Add to the specific round bucket
                    stats_by_round[round_name][name] = ppr
                    
        except Exception as e:
            st.error(f"Error fetching data for {round_name}: {e}")
            
    return stats_by_round

# --- STREAMLIT UI ---
st.set_page_config(page_title="Playoff Fantasy Tracker", layout="wide")
st.title("🏈 NFL Playoff Fantasy Tracker")

# Load existing data
current_db = load_data()

# Sidebar controls
st.sidebar.header("Admin Controls")
st.sidebar.caption("Points are automatically assigned to weeks based on API Week Number (1=WC, 2=Div, 3=Conf, 4=SB).")

# --- ADMIN AUTHENTICATION ---
admin_password = st.sidebar.text_input("Enter Admin Password", type="password")

if admin_password == "password123":  # Change this to your desired password
    st.sidebar.success("Admin Mode Active")
    
    # --- FETCH BUTTON (Moved to Sidebar & Protected) ---
    if st.sidebar.button('🔄 Fetch & Save Live Stats (Auto-Detect)'):
        with st.spinner('Fetching live stats for all playoff rounds (Weeks 1-4)...'):
            live_stats_by_round = fetch_live_playoff_stats()
            
            if live_stats_by_round:
                # Iterate through each round returned by the API
                for round_name, player_stats in live_stats_by_round.items():
                    
                    # Only process rounds that actually have data
                    if not player_stats:
                        continue

                    for manager, roster in TEAMS.items():
                        team_round_total = 0
                        round_detail = {} # Store individual player scores for this round
                        
                        for player in roster:
                            # Check name map first
                            api_name = NAME_MAP.get(player, player)
                            pts = player_stats.get(api_name, 0.0)
                            
                            team_round_total += pts
                            round_detail[player] = pts
                        
                        # Update the database for the specific round
                        round_detail["Total"] = round(team_round_total, 2)
                        current_db[manager][round_name] = round_detail
                
                save_data(current_db)
                st.sidebar.success("Scores updated successfully!")
            else:
                st.sidebar.error("Could not retrieve live stats.")

    # --- RESET BUTTON (Protected) ---
    if st.sidebar.button("⚠️ Reset All Data", help="Clears all saved points and resets to zero."):
        # Initialize empty structure
        empty_data = {
            manager: {round_name: {"Total": 0.0} for round_name in PLAYOFF_ROUNDS} 
            for manager in TEAMS
        }
        save_data(empty_data)
        st.rerun()

else:
    if admin_password:
        st.sidebar.error("Incorrect Password")

st.divider()

# --- DISPLAY LEADERBOARD (SUMMARY) ---
summary_data = {}
for manager, rounds in current_db.items():
    summary_data[manager] = {}
    for r, details in rounds.items():
        if isinstance(details, dict):
            summary_data[manager][r] = details.get("Total", 0.0)
        else:
            summary_data[manager][r] = details 

df = pd.DataFrame.from_dict(summary_data, orient='index')
df['Total PPR'] = df.sum(axis=1)
df = df.sort_values(by="Total PPR", ascending=False)

st.subheader("Leaderboard")
st.dataframe(
    df.style.background_gradient(subset=['Total PPR'], cmap='Greens')
    .format("{:.2f}")
)

# --- DETAILED ROSTER BREAKDOWN ---
st.header("Team Rosters & Weekly Breakdown")

for manager, roster in TEAMS.items():
    with st.expander(f"view {manager}'s Team"):
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
        st.dataframe(
            team_df.style.format({r: "{:.2f}" for r in PLAYOFF_ROUNDS + ["Total"]})
            .background_gradient(subset=["Total"], cmap="Blues")
        )
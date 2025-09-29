import time
import re
import requests
import pandas as pd

# =========================
# SETTINGS
# =========================
SEASON = 2025
WEEKS = range(1, 5)
OUTPUT_CSV = "nfl_data.csv"
REQUEST_TIMEOUT = 30
SLEEP_BETWEEN_CALLS = 0.25

SB_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?week={week}&year={year}"
SUMMARY_URL = "https://site.web.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={eid}"

# =========================
# TEAM INFO
# =========================
TEAM_INFO = {
    'ARI': ('NFC', 'West', 'Arizona Cardinals'),
    'ATL': ('NFC', 'South', 'Atlanta Falcons'),
    'BAL': ('AFC', 'North', 'Baltimore Ravens'),
    'BUF': ('AFC', 'East', 'Buffalo Bills'),
    'CAR': ('NFC', 'South', 'Carolina Panthers'),
    'CHI': ('NFC', 'North', 'Chicago Bears'),
    'CIN': ('AFC', 'North', 'Cincinnati Bengals'),
    'CLE': ('AFC', 'North', 'Cleveland Browns'),
    'DAL': ('NFC', 'East', 'Dallas Cowboys'),
    'DEN': ('AFC', 'West', 'Denver Broncos'),
    'DET': ('NFC', 'North', 'Detroit Lions'),
    'GB':  ('NFC', 'North', 'Green Bay Packers'),
    'HOU': ('AFC', 'South', 'Houston Texans'),
    'IND': ('AFC', 'South', 'Indianapolis Colts'),
    'JAX': ('AFC', 'South', 'Jacksonville Jaguars'),
    'KC':  ('AFC', 'West', 'Kansas City Chiefs'),
    'LV':  ('AFC', 'West', 'Las Vegas Raiders'),
    'LAC': ('AFC', 'West', 'Los Angeles Chargers'),
    'LAR': ('NFC', 'West', 'Los Angeles Rams'),
    'MIA': ('AFC', 'East', 'Miami Dolphins'),
    'MIN': ('NFC', 'North', 'Minnesota Vikings'),
    'NE':  ('AFC', 'East', 'New England Patriots'),
    'NO':  ('NFC', 'South', 'New Orleans Saints'),
    'NYG': ('NFC', 'East', 'New York Giants'),
    'NYJ': ('AFC', 'East', 'New York Jets'),
    'PHI': ('NFC', 'East', 'Philadelphia Eagles'),
    'PIT': ('AFC', 'North', 'Pittsburgh Steelers'),
    'SEA': ('NFC', 'West', 'Seattle Seahawks'),
    'SF':  ('NFC', 'West', 'San Francisco 49ers'),
    'TB':  ('NFC', 'South', 'Tampa Bay Buccaneers'),
    'TEN': ('AFC', 'South', 'Tennessee Titans'),
    'WSH': ('NFC', 'East', 'Washington Commanders'),
}

# =========================
# UTILITIES
# =========================
def get_json(url):
    r = requests.get(url, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json()

def digits_from_display(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    m = re.search(r"[-+]?\d+(\.\d+)?", str(val))
    return float(m.group(0)) if m else None

def get_game_list(season, week):
    data = get_json(SB_URL.format(week=week, year=season))
    games = []
    for ev in data.get("events", []):
        eid = ev.get("id")
        comp = (ev.get("competitions") or [{}])[0]
        competitors = []
        for c in comp.get("competitors", []):
            team = c.get("team") or {}
            competitors.append({
                "homeAway": c.get("homeAway"),
                "abbrev": team.get("abbreviation") or team.get("shortDisplayName"),
                "points": digits_from_display(c.get("score")),
            })
        if eid and len(competitors) == 2:
            games.append({"event_id": eid, "competitors": competitors})
    return games

def fetch_summary(eid):
    return get_json(SUMMARY_URL.format(eid=eid))

def extract_from_summary(summary_json):
    header_competitors = (((summary_json.get("header") or {}).get("competitions") or [{}])[0].get("competitors") or [])
    meta_by_side = {}
    for c in header_competitors:
        side = c.get("homeAway")
        team = c.get("team") or {}
        if side:
            meta_by_side[side] = {
                "abbrev": team.get("abbreviation") or team.get("shortDisplayName"),
                "points": digits_from_display(c.get("score")),
            }

    box = summary_json.get("boxscore") or {}
    teams = box.get("teams") or []
    if len(teams) != 2:
        return []

    recs = []
    for t in teams:
        side = t.get("homeAway")
        stats = {}
        for s in t.get("statistics", []) or []:
            val = digits_from_display(s.get("displayValue"))
            stats[s.get("name")] = val
            stats[s.get("shortDisplayName")] = val
        meta = meta_by_side.get(side, {})
        recs.append({
            "abbrev": meta.get("abbrev"),
            "points": meta.get("points"),
            "total_yards": stats.get("totalYards") or stats.get("Total Yards"),
            "passing_yards": stats.get("netPassingYards") or stats.get("Net Passing Yards"),
            "rushing_yards": stats.get("rushingYards") or stats.get("Rushing Yards"),
            "turnovers": stats.get("turnovers", stats.get("Turnovers", 0)) or 0,
            "homeAway": side
        })

    return recs if all(r.get("abbrev") for r in recs) else []

def team_rows_from_records(season, week, A, B):
    rows = []
    for me, opp in ((A, B), (B, A)):
        pf, pa = me["points"], opp["points"]
        result = None if pf is None or pa is None else ("W" if pf > pa else ("L" if pf < pa else "T"))
        conf, div, full_name = TEAM_INFO.get(me["abbrev"], ("", "", me["abbrev"]))
        opp_conf, opp_div, opp_full = TEAM_INFO.get(opp["abbrev"], ("", "", opp["abbrev"]))

        if conf and div and not div.startswith(conf):
            div = f"{conf} {div}"
        if opp_conf and opp_div and not opp_div.startswith(opp_conf):
            opp_div = f"{opp_conf} {opp_div}"

        rows.append({
            "Week": week,
            "Team": me["abbrev"],
            "Team Full Name": full_name,
            "Conference": conf,
            "Division": div,
            "Opponent": opp["abbrev"],
            "Opponent Full Name": opp_full,
            "Opponent Division": opp_div,
            "Home/Away": me["homeAway"].capitalize(),
            "Result": result,
            "Win Flag": int(result == "W") if result else None,
            "Loss Flag": int(result == "L") if result else None,
            "Tie Flag": int(result == "T") if result else None,
            "Points For": pf,
            "Points Against": pa,
            "Total Yards": me["total_yards"],
            "Yards Allowed": opp["total_yards"],
            "Passing Yards": me["passing_yards"],
            "Passing Yards Allowed": opp["passing_yards"],
            "Rushing Yards": me["rushing_yards"],
            "Rushing Yards Allowed": opp["rushing_yards"],
            "Turnovers": me["turnovers"],
            "Takeaways": opp["turnovers"],
        })
    return rows

# =========================
# MAIN
# =========================
def main():
    all_rows = []
    for wk in WEEKS:
        print(f"Week {wk}: fetching game IDs…")
        try:
            games = get_game_list(SEASON, wk)
        except Exception as e:
            print(f"  Failed to fetch week {wk}: {e}")
            continue

        print(f"  Found {len(games)} games")
        for g in games:
            eid = g["event_id"]
            try:
                summary = fetch_summary(eid)
                recs = extract_from_summary(summary)
                if len(recs) == 2:
                    all_rows.extend(team_rows_from_records(SEASON, wk, recs[0], recs[1]))
                else:
                    print(f"  Couldn't parse stats for event {eid}")
            except Exception as e:
                print(f"  Error fetching event {eid}: {e}")
            time.sleep(SLEEP_BETWEEN_CALLS)

    df = pd.DataFrame(all_rows)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"✅ Done! {len(df)} rows written to '{OUTPUT_CSV}'.")

if __name__ == "__main__":
    main()

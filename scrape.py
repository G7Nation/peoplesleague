# use python 2.7 because 3.x is for chumps

import sys
import json
import datetime
import requests
import logging # not to be used for deforestation
import pprint # pretty printing!
import re # since we have pretty printing, we may as well have ugly regex too

PL_STATS_SKATER = 'skater'
PL_STATS_GOALIE = 'goalie'

PL_STATS_INIT = {}
# use to initialize stats fields for skaters
PL_STATS_INIT[PL_STATS_SKATER] = {               \
    "PIMS":0,                                   \
    "Goals":0,                                  \
    "Assists":0,                                \
    "OT Goals":0,                               \
    "OT Assists":0                              \
}

# use to initialize stats fields for goalies
PL_STATS_INIT[PL_STATS_GOALIE] = {              \
    "PIMS":0,                                   \
    "Starts":0,                                 \
    "Reg W":0,                                  \
    "OT W":0,                                   \
    "Reg SO":0,                                 \
    "OT SO":0,                                  \
    "OT L":0,                                   \
    "Reg L":0                                   \
}

LOGFILE = "peoples.log" # [TODO] make path absolute
BOXSCORE_URL = "https://www.hockey-reference.com/boxscores"

regex_start = {}
regex_end = {}
# the skater stats table starts with all_<3-letter team abbreviation>_skaters
# and ends with a line with total stats, containing TOTAL
regex_start[PL_STATS_SKATER] = re.compile("id=\"all_[A-Z]{3}_skaters")
regex_end[PL_STATS_SKATER] = re.compile("TOTAL")

# in hockey-reference.com's infinite wisdom, they keep track of TOTAL stats
# for skaters, but not for goalies, so just use the </table> end tag to
# find the end
regex_start[PL_STATS_GOALIE] = re.compile("id=\"all_[A-Z]{3}_goalies")
regex_end[PL_STATS_GOALIE] = re.compile("/table")

logging.basicConfig(filename=LOGFILE, level=logging.INFO)
pp = pprint.PrettyPrinter(indent=4)


# wrapper to make logging info stuff for testing/debugging
# it's times like these I long for C's preprocessor
def log_info(title, obj):
    obj_str = pp.pformat(obj)
    logging.info("%s:" %title)
    logging.info(obj_str)

# wrapper for extracting field values from a line of text
# we tend to care about things like goals_against for goalies
#
# return the field's value as a string, or None on error
def extract_value(text, field_name):
    offset = text.find(field_name)
    if offset == -1:
        logging.error("No field name %s in: %s" %(field_name, text))
        return None
    # an example for the "goals against" goalie stat is:
    # <td class="right " data-stat="goals_against" >2</td>
    # we want to extract the value between the closing angle bracket of <td ...>
    # and the opening bracket of </td>, which in this case, is "2"
    start = text.find(">", offset) + 1
    end = text.find("<", offset)
    return text[start:end]

# wrapper for extracting a substring of the html response that contains
# game stats for a team.  if the requested "stat" is invalid, complain loudly.
#
# return start and end offsets in the string if any (there should be both)
def extract_stats_offsets(text, stat):
    start, end = None, None
    try:
        start = regex_start[stat].search(text)
        if start == None:
            logging.error("Stats start index not found: %s" %text)

        end = regex_end[stat].search(text)
        if end == None:
            logging.error("Stats end index not found: %s" %text)

        if start and end:
            # start by starting at the end of start and end by ending at
            # the start of end.  in the end, this will start to make sense. 
            start = start.end()
            end = end.start()
    except KeyError:
        logging.error("Invalid value for stat: %s.  Valid values are %s" \
                      %(pos, regex_start.keys()))
    return start, end

# wrapper to create substring containing one team's player stats.
def make_request(url):
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        #lines = res.text.split('\n')
        #return lines
        return res.text
        
    except requests.exceptions.HTTPError as e:
        logging.error("HTTP Error: %s" %str(e))
    except requests.exceptions.Timeout:
        logging.error("Connection Timed out.")
    except requests.exceptions.TooManyRedirects:
        logging.error("Too Many Redirects.")
    except requests.exceptions.RequestException as e:
        logging.error("Request Exception: %s" %str(e))
    logging.error(str(sys.exc_info()))
    logging.error("Failed to make request to url: %s" %url)
    # return []
    return ""

# per period, a name followed by his goal count so far in parentheses, then
# each assistant on the following lines.  apparently hockey-reference has
# no particular fear of extraneous white space:
#
# <tr class='thead onecell'><th colspan="3">2nd Period</th></tr>
#
# <tr>
#     <td class="right">02:42</td>
#     <td><a href="/teams/NSH/2017.html">NSH</a></td>
#     <td>
#
#
#
#
#
#         <a href="/players/w/watsoau01.html">Austin Watson</a> (1)
#         <a href="/players/j/johanry01.html">Ryan Johansen</a>
#         and <a href="/players/e/ekholma01.html">Mattias Ekholm</a>
#     </td>
# </tr>
def scoring_summary(html):
    goals = []
    assists = []
    ot = 0 # set to 1 if in overtime

    lines = html.split("\n")
    for line in lines:
        if line.find("OT") != -1:
            ot = 1
        if line.find("players") != -1:
            start = line.find(">") + 1
            end = line.rfind("<")
            if line.find("(") != -1:
                goals.append({"name":line[start:end], "ot":ot})
            else:
                assists.append({"name":line[start:end], "ot":ot})
    log_info("Goals", goals)
    log_info("Assists", assists)
    return goals, assists

# example penalty:
# <tr>
#        <td class="right">17:47</td>
#        <td><a href="/teams/ANA/2017.html">ANA</a></td>
#        <td><a href="/players/w/wagnech01.html">Chris Wagner</a>: Roughing &mdash; 2 min</td>
# </tr>
def penalty_summary(html):
    penalties = []
    ot = 0 # set to 1 if in overtime...does this matter for penalty minutes?

    lines = html.split("\n")
    for line in lines:
        if line.find("OT") != -1:
            ot = 1
        if line.find("players") != -1:
            start = line.find(">") + 1
            end = line.rfind("<")
            penalties.append(line[start:end])
    log_info("Penalties", penalties)
    return penalties

# wrapper for extracting game scores and return as dict {"Team Name": num_goals}
def extract_game_score(html):
    scores = {}
    lines = html.split("\n")
    for i in range(0, len(lines)):
        line = lines[i]
        if line.find("div class=\"score\"") != -1: # appears twice
            # lets get ugly!
            name = extract_value(line[i-3], "name")
            score = extract_value(line[i], "score")
            scores[name] = score

    return scores

# parse per-skater game stats, return dict in the form of
# {
#     player_name1:{stat1:value1, stat2:value2, ...},
#     player_name2:{stat1:value1, stat2:value2, ...}
# }
def parse_player_stats(html, stat_type):
    stats = {}
    offset = 0
    ot = 0 # set to 1 if game decided in OT
    so = 0 # set to 1 if there's a shutout

    # most games involve only two teams, so we have to do this twice
    for i in range(0,2):
        text = html[offset:]
        start, end = extract_stats_offsets(text, stat_type)
        if not start or not end:
            # error is logged in above function
            return {}

        offset = end
        text = html[start:end]

        lines = text.split("\n")
        for line in lines:
            if line.find("players") != -1:
                # player names are links, take advantage of extract_value
                # by using "players", which appears in the link before
                # the player's name, as opposed to the stat name which apepars
                # in the HTML as data-stat="player"
                name = extract_value(line, "players")

                # conveniently, goalies can have penalty minutes too, so I
                # can be generic about this statistic.  a 2011 study found
                # that the most common goalie penalty is deking Wayne
                # Gretzky, which was deemed illegal in 1996:
                # https://www.youtube.com/watch?v=DD419PXwGoA
                pim = extract_value(line, "pen_min")

                # we have to use scoring summary to fill in goals/assists values
                stats[name] = PL_STATS_INIT[stat_type]
                stats[name]["PIMS"] = pim # penalty minutes are universal

                #log_info("Added to stats", (name, stats[name]))

    # we need to parse scoring summary for both skaters and goalies since
    # it's the only way we can distinguish regulation time from overtime
    # points
    goals, assists = scoring_summary(html)

    # fill in goals/assists stats for skaters
    # [TODO]  move player-type-specific stat recording to separate function
    # accessible by indexing into a dict
    if stat_type == PL_STAT_SKATER:
        for goal in goals:
            if goal['ot'] == 0:
                stats[goal['name']['Goals']] += 1
            else:
                ot = 1 # game decided in OT.  need this for goalie stats
                stats[goal['name']['OT Goals']] += 1

        for assist in assists:
            if assist['ot'] == 0:
                stats[assist['name']['Assists']] += 1
            else:
                stats[assist['name']['OT Assists']] += 1

    # determining goalie stats in The People's League based on the info
    # we can scrape from hockey-reference.com is a pain in the ass in terms
    # of figuring out a generic processes
    elif stat_type == PL_STATS_GOALIE:
        # [TODO] implement a generic solution for goalies.  for now,
        # let's just get a hack that works.
        scores = extract_game_score(html) # gives us {name, score} for team name
        k = scores.keys()
        if scores[k[0]] == 0 or scores[k[1]] == 0:
            so = 1 # we have a shutout
        if scores[k[0]] > scores[k[1]]: # team 1 beats team 2
            winner = 0
        else:
            winner = 1
            if ot == 0:
                if so == 0:
                    stats[k[winner]]["Reg W"] = 1
                else:
                    stats[k[winner]]["Reg SO"] = 1
                stats[k[abs(winner-1)]]['Reg L'] = 1 # record Reg loss
            else:
                if so == 0:
                    stats[k[winner]]['OT W'] = 1
                else:
                    stats[k[winner]]['OT SO'] = 1
                stats[k[abs(winner-1)]]['OT L'] = 1 # record OT loss

    return stats

# parse per-goalie game stats, return dict in the form of
# {
#     player_name1:{stat1:value1, stat2:value2, ...},
#     player_name2:{stat1:value1, stat2:value2, ...}
# }
def parse_goalie_stats(html):
    stats = {}
    offset = 0

    # as most games involve only two teams, we have to do this twice
    for i in range(0,2):
        text = html[offset:]
        start, end = extract_goalie_stats_offsets(text)
        if not start or not end:
            # error is logged in above function
            return {}

        offset = end
        text = html[start:end]

        lines = text.split("\n")
        for line in lines:
            if line.find("players") != -1:
                # player names are links, take advantage of extract_value
                # by using "players", which appears in the link before
                # the player's name
                name = extract_value(line, "players")
                print("Name = %s" %name)
                pim = extract_value(line, "pen_min")

                # we have to use scoring summary to fill in goals/assists values
                stats[name] = {"PIMS":pim,
                               "Goals":0,
                               "Assists":0,
                               "OT Goals":0,
                               "OT Assists":0}

def parse_boxscore(url):
    html = make_request(url)
    stats = parse_player_stats(html, PL_STATS_SKATER)
    pprint.pprint(stats)


def get_boxscores(url):
    yesterdate = datetime.utcnow()
    # yesterday's date, UTC -5 for EST, not that it really matters
    yesterdate -= datetime.timedelta(days=1, hours=5)
    date_str = yesterdate.strftime("%Y%m%d")

    res = make_request(url)

    lines = res.split("\n")
    for line in lines:
        start = line.find("\"") + 1
        end = line.rfind("\"")
        if line.find(date_str) != -1:
            boxurl = line[start:end]
            boxurl = "www.hockey-reference.com/%s" %boxurl
            parse_boxscore(boxurl)


# XXX testing
parse_boxscore("https://www.hockey-reference.com/boxscores/201705120ANA.html")

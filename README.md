# Loanbot: An automated Twitter/X client for tweeting player match info
Loanbot is a tool that was originally designed to keep up to date with the performances and games of Chelsea FC loan players. Many Twitter accounts have attempted to provide manual updates on players, but over time this process gets too arduous, players are forgotten and the process is abandoned. This project relieves the strain on this process by automating the collection of data regarding a specified list of players, extracts meaningful information and tweets out the desired update. The Twitter account can be found here at https://twitter.com/CFCLoanBot.

## Design
The tool works by scraping data from FotMob, using the MobFot package (https://github.com/bgrnwd/mobfot) as a base, although this is essentially just a wrapper around a GET request to their site. Every hour, every player on the list is checked, and their next fixture is extracted. If this next fixture is within the next hour or less, then it is presumed that the players lineup exists. At this stage, the player is added to a queue. 

Every minute, for every player in the queue, the match details are polled. When certain events such as the player existing in the lineup, the match starting, the player scores/assists, is carded, subbed on or off, or the game finishes, an event is triggered which causes a tweet to be sent out. When the match finishes, the player is removed from the queue so that the API is not spammed with unnecessary requests.  

## Installation
First, clone the repository:
```
git clone https://github.com/tomaldridge12/loanbot.git
```  
A requirements file will be shortly provided to assist in the installation process. Until then, requirements must be installed manually.

## Usage
Edit the `ids.json` file, and provide each player in the format:
```
"Player" : {
    "id" : PLAYER_ID,
    "team_name": TEAM_NAME,
    "team_id": TEAM_ID
},
```
where PLAYER_ID and TEAM_ID can be extracted from the player/team URL on FotMob. Twitter/X API keys will also be required to tweet updates, and these should be stored in a `.env` file within the source directory. Finally, run `python main.py` in order to start the bot.


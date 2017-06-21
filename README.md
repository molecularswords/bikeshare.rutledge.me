# Capital Bikeshare Route Finder

[bikeshare.rutledge.me](http://bikeshare.rutledge.me)

## Introduction

Have you ever made plans to utilize a service only to find that it was temporarily unavailabile when you went to use it? This can be especially disrupting of our lives when it comes to transportation services. A missed flight, a late bus, or excessive traffic can effectively ruin a trip since arriving on time is often of paramount importance for accomplishing the trip's purpose. Users of bikeshare networks experience this with unfortunate frequency due to the non-uniform geographical distribution of bike station usage without a compensatory increase in bikes and docks at heavily used stations. This discordance between network usage and resource allocation causes bike or dock availability to rapidly decline at certain high-volume usage stations during periods of heavy activity and can result in lost time and potential disruption of plans as the user scrambles to find a bike or a dock at other nearby stations. This tool is for all those bikeshare users in DC who have experienced this frustrating reality firsthand as well as anyone who wants to avoid it.

## Purpose

This tool aims to provide the user with information about how to best plan their route when using the Capital Bikeshare system in Washington, D.C. It uses simple statistical models trained on historical usage data to predict the availability of bikes and docks at any given time during the week for each station within the network. The route finder utilizes these data to find the optimal route from a user-defined pair of start and end stations that will provide the user with a high probability of being able to get a bike at the start station and to dock that bike at the end station. If the user picks a station that is predicted to have few to no bikes (for start stations) or docks (for end stations) available then the route finder will automatically choose the closest station that does have adequate availability. Furthermore, if the user's trip ends up being predicted to last around 30 minutes or more then the route finder will also pick the optimal waypoints along the route so the user can switch bikes to avoid paying the fee incurred for single rides longer than 30 minutes.

## Implementation

The route finder is presented as a web app where users can select start and end points as well as the day of the week and the time of their trip. Stations can be selected either from dropdown lists or by clicking on markers on the Google Map showing the station network. Short clicking selects the start station (colored red) and long clicking selects the end station (colored blue). When the stations and time are selected the user clicks the "Find best route" button (a bug currently requires two clicks of this button for the full route with waypoints to be shown, sorry again) to see the directions for the optimal route. The route times and directions are deterimined using Google Directions service in bicycle mode. I find that Google tends to underestimate the amount of time needed to complete a trip, so waypoints (colored grey) are selected at intervals of around 24 minutes. To choose a different route the user simply repeats the process.

## The Algorithm

The data used as input to the route finder algorithm are current station data, including geographic location and number of available bikes and docks, that are gathered from the Capital Bikeshare website at 10 minute intervals and aggregated over a 4 week period. Predictions of future availability are made using these availability data as well as insights from an analysis of historical trip data provided by the Capital Bikeshare website. The previous 4 weeks' availability data are smoothed using an exponentially-weighted moving average to remove spikes in the data and are then grouped by day of the week and averaged to produce an availability prediction. This may sound overly simplistic, but it is informed by an analysis of the historical data showing that the time of day and the day of the week are by far the most predictive features of individual station availability with other features like the weather or whether or not the day is a holiday having a significant but lesser impact (see the Data Analysis and Results for more on this).

These averaged time series data are used as input for a pair of conditional checks carried out on the stations selected by the user as well as any potential waypoint stations automatically selected by the algorithm. The first of these checks deterimines if the starting station is predicted to have at least 3 bikes available at the specified time. If so then this station is used as the embarkation point. If not then a k-nearest neighbors method is called to find the 10 closest stations to the station ranked in order of closest to furthest, and the conditional check is applied to each of these stations sequentially until one is found to satisfy the condition. This station is then chosen as the new starting station along with a notification being displayed to the user that the starting station changed due to low probability of availability at the originally chosen station. The algorithm then goes through the same conditional check process for the ending station except that it checks for dock availability instead of bike availability.

Once the embarkation and docking stations are determined the algorithm then makes an API call to the Google Directions service to determine the optimal cycling route broken down into steps containing data about the geographic location and time needed to complete each step. Another conditional check is then performed to determine if the total time of the trip is less than 24 minutes. If so then no waypoints are chosen and the route is displayed with the final directions. If not, however, then the time needed to complete each step along the route is sequentially added to the previous step's time until the growing time variable becomes greater than or equal to 24. The previous step's end point is then parsed for its geographic location which is used as input for the k-nearest neighbors method from the previous steps. The method checks for waypoints that have at least 3 bikes and docks available and returns the closest one. At this point the time variable is reset and the process of finding the next waypoint begins anew. This process is repeated until the docking station is reached. The algorithm then makes another Google Directions API call with updated waypoints to get the final directions set, which is displayed to the user.

## Data Analysis and Results

- [Data gathering and preparation](https://github.com/molecularswords/molecularswords.github.io/blob/master/scripts/data_wrangling.ipynb)
- [Data analysis](https://github.com/molecularswords/molecularswords.github.io/blob/master/scripts/EDA.ipynb)
- [Modeling](https://github.com/molecularswords/molecularswords.github.io/blob/master/scripts/modeling.ipynb)


## Future Features

- Implement a regression-based prediction method that includes other features like:
	- temperature
	- precipitation
	- holidays
	- city events (like sporting events, political rallies, et cetera)
- Add current bike and dock availability visual indicators to each Google Maps station marker

##### Fun tip

Go back and read the first few sentences of the first paragraph in your best infomercial personality voice while envisioning the depicted scenarios acted out with world-shattering, unrealistically hyperbolic drama and frustration. Extra points and a gold star if you naturally did that on first read.

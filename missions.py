# %% Prepare crewstand missions from STREaM output
"""
We now have the STREaM optput data for 20 houses over one month. The output is provided in `.csv`  files, one for each house. We must transfer it into the `.json` format that is used by the crewstand missions. Furthermore we must manipulate some events as they are long (up to ~ 45 minutes). As the crewstand shall be used for exposition purposes it will not be of spectators interest to watch 45 minutes constant water flow. Therfore, we will scale long events to be shorter than 60 seconds.
"""
import json
import pandas as pd
from pydantic.json import pydantic_encoder


from models import *

# %% import generated data
file_base = "House_10sec_1month_109"
house = pd.read_csv(file_base + ".csv")
# %%initiate events df
missions = pd.Series()
# %% Identify water consumption events
end_uses = ["Toilet", "Faucet", "ClothesWasher", "Dishwasher", "Shower", "Bathtub"]
for current_end_use_id, current_end_use in enumerate(end_uses):
    is_active = pd.Series(house[current_end_use] > 0, dtype=int)
    # Identify when the end-use was switched on / off
    switch_events = is_active.diff()
    switch_on_idxs = switch_events[switch_events == 1].index
    switch_off_idxs = switch_events[switch_events == -1].index

    # Transform each event in a FlowControlMission
    end_use_missions = []
    event_idxs = []
    for i, _ in enumerate(switch_on_idxs):
        switch_off_idx = switch_off_idxs[i]
        switch_on_idx = switch_on_idxs[i]
        event = house[current_end_use].iloc[switch_on_idx:switch_off_idx]
        # Convert form l / 10s to l / min
        event = event * 6
        peak = event.max()
        # filter out events with a peak > 20 l / min as it is out of range for crewstand
        if peak <= 20:
            duration = (switch_off_idx - switch_on_idx) * 10
            scaling_factor = int(duration / 60.1) + 1
            # scale Events longer 60 s to be within 60 s duration
            seconds_per_step = 10 / scaling_factor
            new_mission = FlowControlMission(
                valve_id=current_end_use_id,
                duration_scaling_factor=scaling_factor,
                actual_end_use=current_end_use,
                actual_start_time=house["TS"].iloc[switch_on_idx],
                flow_trajectory=[
                    TrajectoryPoint(
                        flow_rate=event.iloc[i], time=(i + 1) * seconds_per_step
                    )
                    for i in range(len(event))
                ],
            )
            end_use_missions += [new_mission]
            event_idxs += [switch_on_idx]
    #
    new_missions = pd.Series(end_use_missions, index=event_idxs)
    missions = pd.concat([missions, new_missions])
# %% sort
missions.sort_index(inplace=True)
# %% Write to mission file
with open(file_base + "_mission.json", "w") as f:
    json.dump(missions.to_list(), f, default=pydantic_encoder)

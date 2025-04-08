import json
import pandas as pd
import os
import glob
from pydantic.json import pydantic_encoder
from models import *


def process_house_data(file_base):
    """
    Processes water consumption data for a house from STREaM output CSV files.

    This function reads a specified CSV file containing water consumption
    data for a house over a period. It identifies water consumption events
    for several end-uses, scales long events to be less than 60 seconds, and
    generates `FlowControlMission` objects. These missions control flow rates
    for a crewstand simulation system.

    Parameters
    ----------
    file_base : str
        The base filename of the STREaM CSV output file, excluding the extension.

    Returns
    -------
    missions : pd.Series
        A pandas Series where each item represents a `FlowControlMission`
        object encapsulating start time, scaled duration, and flow trajectory
        of a water consumption event for end-uses like toilets, faucets,
        showers, etc.

    Raises
    ------
    FileNotFoundError
        If the specified CSV file cannot be found.
    pandas.errors.ParserError
        If the CSV file cannot be parsed correctly.

    Warns
    -----
    UserWarning
        If the peak water usage during an event exceeds 20 liters per minute,
        or lower than 1 liter per minute that event will be skipped
        (it is out of the crewstand's operational range).

    Notes
    -----
    * The CSV file is expected to have columns representing various end-uses:
      "Toilet", "Faucet", "ClothesWasher", "Dishwasher", "Shower", and "Bathtub".
    * "TS" column should be in the CSV to record the timestamp of each reading.
    * Only events with a peak flow rate ≤ 20 liters/minute are considered.
    * Each CSV file row represents a 10-second interval of data.

    See Also
    --------
    FlowControlMission : class that defines the mission structure.
    TrajectoryPoint : class that defines a point on the flow trajectory.

    Examples
    --------
    >>> from missions import process_house_data
    >>> house_missions = process_house_data('House_10sec_1month_109')
    >>> print(house_missions)

    This would process the CSV file named "House_10sec_1month_109.csv" and return
    a pandas Series of `FlowControlMission` objects.

    """
    house = pd.read_csv(file_base + ".csv")

    missions = pd.Series()
    end_uses = ["Toilet", "Faucet", "ClothesWasher", "Dishwasher", "Shower", "Bathtub"]

    for current_end_use_id, current_end_use in enumerate(end_uses):
        is_active = pd.Series(house[current_end_use] > 0, dtype=int)
        switch_events = is_active.diff()
        switch_on_idxs = switch_events[switch_events == 1].index
        switch_off_idxs = switch_events[switch_events == -1].index

        end_use_missions = []
        event_idxs = []
        for i, _ in enumerate(switch_off_idxs):
            switch_off_idx = switch_off_idxs[i]
            switch_on_idx = switch_on_idxs[i]
            event = house[current_end_use].iloc[switch_on_idx:switch_off_idx]
            event = event * 6
            peak = event.max()
            if peak <= 20 and peak >= 0.1:
                duration = (switch_off_idx - switch_on_idx) * 10
                scaling_factor = int(duration / 60.1) + 1
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
                end_use_missions.append(new_mission)
                event_idxs.append(switch_on_idx)
        new_missions = pd.Series(end_use_missions, index=event_idxs)
        if not new_missions.empty:
            missions = pd.concat([missions, new_missions])

    missions.sort_index(inplace=True)
    return missions


def generate_missions(stream_output_folder: str = "./"):
    """
    Generates mission JSON files from STREaM output data in CSV format.

    This function searches a specified directory for CSV files which contain
    STREaM output data for houses, then transforms and scales this data to
    generate `FlowControlMission` objects. The resulting missions are saved
    as JSON files with the naming convention: `<original csv file basename>_mission.json`.

    These JSON files are used by a crewstand simulation system for visualization
    and analysis purposes.

    Parameters
    ----------
    stream_output_folder : str, optional
        The path to the directory containing the STREaM output CSV files.
        Defaults to the current directory ("./").

    Returns
    -------
    None

    Generates JSON files in the specified output directory.

    Raises
    ------
    OSError
        If the specified `stream_output_folder` path is not accessible.

    Notes
    -----
    * The function assumes that the `models.py` module with definitions
      for `FlowControlMission` and `TrajectoryPoint` is present.
    * CSV file names must start with "House_" and end with ".csv".
    * Each long event in the CSV files is scaled to be less than 60 seconds.

    See Also
    --------
    process_house_data: function that processes a single CSV file.

    Examples
    --------
    >>> generate_missions("./STREaM_out/")

    This will process all CSV files in the "STREaM_out/" directory and write the
    corresponding JSON mission files back to the same directory.
    """

    # Finding all house CSV files in the stream output folder
    csv_list = glob.glob(os.path.join(stream_output_folder, "House_*.csv"))

    for file_path in csv_list:
        file_base = os.path.splitext(os.path.basename(file_path))[0]
        missions = process_house_data(file_base)
        output_file = os.path.join(stream_output_folder, file_base + "_mission.json")

        with open(output_file, "w") as f:
            json.dump(missions.to_list(), f, default=pydantic_encoder)


if __name__ == "__main__":
    generate_missions()

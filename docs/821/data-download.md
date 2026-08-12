# Data Download Procedures (Type 1 821-env systems)

## Overview
Data download process for Type 1 821-env systems

## Notes Before Downloading
- Before downloading and placing data into the respective folders, ensure that the serial numbers of the equipment match the data sheet serial numbers.
- Data should be stored as follows:
- Highest level: Deployment folder in SITE000_YYYYMMDD
- Next level: AUDIO, MET, METADATA, RAW
- Data process: Song Meter files go to AUDIO, wind data logger microSD goes to MET, data sheets and images go to METADATA, and LD 821env SPL meter data goes to RAW.
- Data Logger Card (microSD)The data logger is in the white plastic box with the NSNSD logo and records data from the wind sensor.
- Check the serial number under the white lid and make sure it matches the data sheet.

## Data Logger (microSD)
- Insert the microSD card into the microSD-to-USB adapter and navigate to the card in Windows Explorer.
- Select all files (MD files and datestamped CSVs).
- Copy all files to the MET subfolder within the deployment folder (NOTE: ensure you are in the correct folder by matching it to the datasheet).
- Confirm that all files copied from the microSD card by comparing the number of files in each location (copiedto and copiedfrom).
- Once you are confident that all data has been transferred into the deployment folder, delete the files from the microSD card by selecting and deleting them or by rightclicking and formatting the card.
- Place the microSD card back into the data logger so it is ready for the next deployment.
- Wildlife Acoustics Song Meter Mini SD CardThe Song Meter is the small green plastic box with the small microphone.
- Remove the SD card from the Song Meter and insert it into your laptop.
- Navigate to the SD card in Windows Explorer and ensure that data is present. You should see a summary text file and a data folder containing audio files in .wav format. Explore the data to check that:a) all file sizes are the same (except the first couple of files and possibly the last),b) files are written by the hour, andc) dates reflect the deployment period.

## Song Meter Mini (SD Card)
- A typical deployment will produce a large volume of data, so this step may take a while. Consider moving on to SPL download while the .wav files are copying.
- Confirm that all files copied from the SD card by comparing the number of files in each location (copiedto and copiedfrom).
- Listen to a subset of files in the deployment's AUDIO folder to confirm that the recording successfully collected data. If audio issues are present, confirm whether they appear in both locations before moving to the next step.
- Once you are confident that all data has been transferred into the deployment folder, delete the files from the SD card by selecting and deleting them or by rightclicking and formatting the card.
- Place the SD card back into the same Song Meter so it is ready for the next deployment.
- Ensure that the Song Meter is still turned off.
- Larson Davis Unit
- 

## Larson Davis 821-env SPL Meter Download
- This is the sound level meter and must be disconnected from the power source, the microphone cable, and the battery secure plate.
- Connect the 821env SPL meter to the computer using a USBC cable.
- Open G4 LD Utility.
- Doubleclick on the serial number of the appropriate unit.
- A new window will appear with all stored data on the unit. Find the deployment by matching the date in the list of files. It will likely be the first selection.
- Click the checkbox next to the date/file in the primary pane.
- Click “Download” in the toolbar above and monitor download progress on the right side of the primary pane.
- Once downloaded, doubleclick the file you selected in step 6. This and the previous step may take some time, especially for a 30day deployment.
- After the data opens in G4 Utility, you may explore the data here before downloading if you choose.
- When finished, go to the main menu, select the “File” dropdown, and click “Export to CSV.” After some time, a popup will appear indicating that the files have downloaded, along with the file location. You have two options:a. Select OK and manually navigate to:C:\Users\Public\Documents\PCB Piezotronics\G4\Metersorb. In the popup, select View Location, which will take you directly to the data.
- Once at the download location, ensure you find the serial number and deployment date for the meter and the data of interest. This can become confusing as you download more data because G4 saves all downloads here by serial number and deployment date.
- After confirming the correct data, select the folder and ensure it contains the following files: OBA, Session Log, Settings, Summary, and Time History files. Time History files will have a numerical suffix for longer deployments—expect up to three Time History files for a 30day deployment.
- Copy the folder containing all CSVs and paste it into the **RAW** folder of the appropriate deployment.

G4 Utility organizes exports under the PC by meter serial number, then by deployment date:

- **Serial number folder** — all downloads for that LD821 unit
- **Deployment date folder** — one deployment’s CSV set (OBA, Session Log, Settings, Summary, Time History)

Copy the **deployment date folder** (the one that contains the Time History CSVs) into your deployment’s `RAW/` directory. Do **not** use a separate `SPL/` folder — older docs sometimes used that name; the standard layout for this repo is `RAW/` (see [`pipeline.md`](pipeline.md)).

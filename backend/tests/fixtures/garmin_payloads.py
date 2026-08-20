GARMIN_ACTIVITY_PAYLOAD = {
    "activityId": 987654321,
    "activityName": "Morning Run",
    "activityType": {"typeKey": "running"},
    "startTimeGMT": "2027-01-01 22:30:00",
    "distance": 10025.4,
    "duration": 3661.2,
    "averageHR": 142,
    "elevationGain": 84.3,
    "calories": 610,
    "unsupportedNestedValue": {"ignored": True},
}


GARMIN_DAILY_HEALTH_PAYLOAD = {
    "calendarDate": "2027-01-01",
    "get_rhr_day": {"restingHeartRate": 47},
    "get_sleep_data": {"dailySleepDTO": {"sleepTimeSeconds": 28800}, "sleepScores": {"overall": {"value": 82}}},
    "get_hrv_data": {"hrvSummary": {"lastNightAvg": 56, "weeklyAvg": 52}},
    "get_stress_data": {"avgStressLevel": 21},
    "get_steps_data": {"totalSteps": 12345},
}

from datetime import date, timedelta


def next_weekday(value, weekday):
    days_until_weekday = (weekday - value.weekday()) % 7
    return value + timedelta(days=days_until_weekday)

// web-app/src/packages/core/util/src/date/DateUtil.ts
const DAY_MS = 24 * 60 * 60 * 1000;

export function startOfDay(value: Date | number = Date.now()): Date {
  const date = new Date(value);
  // 0 分别把时、分、秒、毫秒全部归零
  date.setHours(0, 0, 0, 0);
  return date;
}

export function getCalendarDayDistance(
  value: Date | number,
  now: Date | number = Date.now(),
): number {
  return Math.floor(
    (startOfDay(now).getTime() - startOfDay(value).getTime()) / DAY_MS,
  );
}

export function getMonthParts(value: Date | number): {
  year: number;
  month: number;
} {
  const date = new Date(value);
  return { year: date.getFullYear(), month: date.getMonth() + 1 };
}

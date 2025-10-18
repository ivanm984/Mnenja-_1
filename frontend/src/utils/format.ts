export function formatFileSize(size?: number): string {
  if (!size) {
    return '0 B';
  }

  const units = ['B', 'KB', 'MB', 'GB'];
  let value = size;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }

  return `${value.toFixed(unitIndex === 0 ? 0 : 2)} ${units[unitIndex]}`;
}

export function formatTimestamp(value?: string | number | Date): string {
  if (!value) {
    return '';
  }

  try {
    return new Date(value).toLocaleString('sl-SI');
  } catch (error) {
    console.warn('Unable to format timestamp', error);
    return '';
  }
}

export function stringId(value: unknown): string {
  if (value === undefined || value === null) {
    return '';
  }

  return String(value);
}

export function ensureText(value: unknown): string {
  if (value === undefined || value === null) {
    return '';
  }

  try {
    return String(value);
  } catch (error) {
    console.warn('Unable to coerce text', error);
    return '';
  }
}

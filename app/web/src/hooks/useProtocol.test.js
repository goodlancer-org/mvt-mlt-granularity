import { afterEach, describe, expect, test, vi } from 'vitest';
import { hasActiveJob, reconvertDataset } from './useProtocol';

afterEach(() => vi.unstubAllGlobals());

const respond = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => body });

describe('reconvertDataset', () => {
  test('asks the API to rebuild the dataset in place and returns the queued job', async () => {
    const fetchMock = vi.fn(async () => respond(202, { job: { name: 'natural_earth_vector', status: 'queued' } }));
    vi.stubGlobal('fetch', fetchMock);

    const job = await reconvertDataset('natural_earth_vector');

    expect(fetchMock).toHaveBeenCalledWith('/api/datasets/natural_earth_vector/reconvert', { method: 'POST' });
    expect(job).toMatchObject({ name: 'natural_earth_vector', status: 'queued' });
  });

  test('never deletes anything: the only request is the POST', async () => {
    const fetchMock = vi.fn(async () => respond(202, { job: { name: 'x', status: 'queued' } }));
    vi.stubGlobal('fetch', fetchMock);

    await reconvertDataset('x');

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls.every(([, init]) => init.method === 'POST')).toBe(true);
  });

  test('escapes the dataset name', async () => {
    const fetchMock = vi.fn(async () => respond(202, { job: {} }));
    vi.stubGlobal('fetch', fetchMock);

    await reconvertDataset('a b/c');

    expect(fetchMock.mock.calls[0][0]).toBe('/api/datasets/a%20b%2Fc/reconvert');
  });

  test('shows the server\'s reason when the source file is missing', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => respond(400, { error: "The source file for 'demo' is missing: /data/sources/demo/demo.zip. The current map has not been touched." })));

    await expect(reconvertDataset('demo')).rejects.toThrow('The current map has not been touched');
  });

  test('shows the server\'s reason when the dataset is already being processed', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => respond(409, { error: "Dataset 'demo' is already being processed." })));

    await expect(reconvertDataset('demo')).rejects.toThrow('already being processed');
  });

  test('has a readable message when the server gives none', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => respond(500, {})));

    await expect(reconvertDataset('demo')).rejects.toThrow('Failed to rerun conversion');
  });
});

describe('hasActiveJob', () => {
  const jobs = [
    { name: 'a', status: 'completed' },
    { name: 'b', status: 'running' },
    { name: 'c', status: 'queued' },
    { name: 'd', status: 'canceling' },
    { name: 'e', status: 'failed' },
    { name: 'f', status: 'canceled' },
  ];

  test.each(['b', 'c', 'd'])('%s is still being converted', (name) => {
    expect(hasActiveJob(jobs, name)).toBe(true);
  });

  test.each(['a', 'e', 'f', 'unknown'])('%s is not', (name) => {
    expect(hasActiveJob(jobs, name)).toBe(false);
  });

  test('tolerates a missing job list', () => {
    expect(hasActiveJob(undefined, 'a')).toBe(false);
  });
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import sharp from 'sharp';

test('official Gemini sends API-key header and reference images without Vertex auth', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'gemini-api-test-'));
  const savedFetch = globalThis.fetch;
  const savedConfig = process.env.IMAGE_GEN_CONFIG;
  const savedKey = process.env.GEMINI_API_KEY;
  try {
    process.env.IMAGE_GEN_CONFIG = join(dir, 'config.json');
    process.env.GEMINI_API_KEY = 'test-key-not-a-secret';
    await writeFile(process.env.IMAGE_GEN_CONFIG, JSON.stringify({backends: {gemini: {
      accounts: [{provider: 'google', api_key_env: 'GEMINI_API_KEY', image_model: 'gemini-3.1-flash-image'}]
    }}}));
    const ref = join(dir, 'ref.png');
    await sharp({create: {width: 8, height: 8, channels: 3, background: 'red'}}).png().toFile(ref);
    const { generateWithGemini } = await import('../dist/_gemini.js');
    let calls = 0;
    globalThis.fetch = async (url, init) => {
      calls++;
      assert.equal(url, 'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-image:generateContent');
      assert.equal(init.headers['x-goog-api-key'], 'test-key-not-a-secret');
      assert.equal(init.headers.Authorization, undefined);
      const body = JSON.parse(init.body);
      assert.equal(body.contents[0].parts.length, 2);
      assert.ok(body.contents[0].parts[1].inlineData.data);
      assert.deepEqual(body.generationConfig.responseModalities, ['TEXT', 'IMAGE']);
      return new Response(JSON.stringify({candidates: [{content: {parts: [
        {inlineData: {data: 'aW1hZ2U=', mimeType: 'image/png'}}
      ]}}]}));
    };
    assert.equal((await generateWithGemini({prompt: 'test', refs: [ref]}))[0].base64, 'aW1hZ2U=');
    assert.equal(calls, 1);
    delete process.env.GEMINI_API_KEY;
    await assert.rejects(generateWithGemini({prompt: 'test', refs: []}), /GEMINI_API_KEY is required/);
    assert.equal(calls, 1);
  } finally {
    globalThis.fetch = savedFetch;
    if (savedConfig === undefined) delete process.env.IMAGE_GEN_CONFIG;
    else process.env.IMAGE_GEN_CONFIG = savedConfig;
    if (savedKey === undefined) delete process.env.GEMINI_API_KEY;
    else process.env.GEMINI_API_KEY = savedKey;
    await rm(dir, {recursive: true, force: true});
  }
});

const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('web/app.js', 'utf8');
const begin = source.indexOf('class LiveDubbingEngine {');
const end = source.indexOf('\nwindow.liveDubbingEngine =', begin);
const context = { console, setTimeout, clearTimeout };
vm.createContext(context);
vm.runInContext(source.slice(begin, end) + '\nthis.Engine = LiveDubbingEngine;', context);
function audio() {
    return { duration: 30, currentTime: 0, paused: true, plays: 0, pause() { this.paused = true; },
        async play() { this.paused = false; this.plays++; } };
}
function video() {
    return { currentTime: 0, paused: false, playbackRate: 1, volume: 1,
        addEventListener() {}, pause() { this.paused = true; }, async play() { this.paused = false; } };
}
(async () => {
    const e = new context.Engine();
    const v = video(), a = audio();
    const subs = [{text:'first', startSeconds:0, endSeconds:2}, {text:'second', startSeconds:2, endSeconds:4}];
    const options = {voiceId:'local_test', speed:1};
    e.cache.set(e.timelineKey(subs,'local_test',1), a);
    await e.syncWithPlayer(v, subs, options);
    for (const t of [0.25, 0.5, 1, 2, 2.5, 3]) {
        v.currentTime = a.currentTime = t;
        await e.syncWithPlayer(v, subs, options);
    }
    assert.equal(a.plays, 1, 'must not replay at timeupdate or sentence boundary');
    e.stop(); v.currentTime = 1.5;
    await e.syncWithPlayer(v, subs, options);
    assert.equal(a.currentTime, 1.5, 'seek resumes in middle of track');
    v.playbackRate = 1.5;
    await e.syncWithPlayer(v, subs, options);
    assert.equal(a.playbackRate, 1.5);
    const e2 = new context.Engine(), v2 = video();
    let resolve;
    e2.prepare = () => new Promise(r => { resolve = r; });
    const pending = e2.syncWithPlayer(v2, subs, options);
    assert.equal(v2.paused, true, 'wait for audio before progressing video');
    e2.stop(); // internal pause event
    e2.stop(); // user switches preview/cancels
    resolve(audio()); await pending;
    assert.equal(v2.paused, true, 'late response cannot restart cancelled preview');
    const e3 = new context.Engine(), v3 = video(), a3 = audio();
    e3.prepare = async () => a3;
    await e3.syncWithPlayer(v3, subs, options);
    assert.equal(v3.paused, false);
    assert.equal(a3.plays, 1);
    assert.notEqual(e.timelineKey(subs,'local_test',1), e.timelineKey([{...subs[0], text:'edited'}],'local_test',1));
    console.log('PASS: continuous playback, boundaries, seeking, speed, buffering, cancellation, edit invalidation');
})().catch(error => { console.error(error); process.exitCode = 1; });

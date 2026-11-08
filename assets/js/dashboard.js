(async () => {
  const status = document.getElementById('status');
  try {
    const response = await fetch('data/books.json', {cache:'no-cache'});
    if (!response.ok) throw new Error('HTTP ' + response.status);
    const books = await response.json();
    if (!Array.isArray(books)) throw new Error('Invalid catalogue');
    const values = [
      ['Imported records', books.length],
      ['With available copies', books.filter(b => b.available_copies > 0).length],
      ['With ratings', books.filter(b => b.openlibrary_rating_average > 0 && b.openlibrary_rating_count > 0).length],
      ['Recent releases', books.filter(b => b.is_recent_release === true).length],
      ['With descriptions', books.filter(b => typeof b.description === 'string' && b.description.trim()).length],
      ['With quality flags', books.filter(b => Array.isArray(b.quality_flags) && b.quality_flags.length).length],
      ['Availability older than 24h', books.filter(b => { const t = Date.parse(b.availability_checked_at); return !Number.isFinite(t) || Date.now()-t > 86400000; }).length]
    ];
    const metrics = document.getElementById('metrics');
    for (const [label, value] of values) {
      const dt = document.createElement('dt'), dd = document.createElement('dd');
      dt.textContent = label; dd.textContent = value.toLocaleString(); metrics.append(dt, dd);
    }
    status.textContent = 'Published catalogue snapshot, not live stock. Missing availability timestamps count as stale.';
  } catch (error) { status.textContent = 'Could not load dashboard: ' + error.message; }
})();
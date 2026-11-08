(async () => {
  const status = document.getElementById('status');
  const metrics = document.getElementById('metrics');
  try {
    const [booksResponse, coverageResponse] = await Promise.all([
      fetch('data/books.json',{cache:'no-cache'}),
      fetch('data/coverage-report.json',{cache:'no-cache'}).catch(() => null)
    ]);
    if (!booksResponse.ok) throw new Error('books.json: HTTP ' + booksResponse.status);
    const books = await booksResponse.json();
    if (!Array.isArray(books)) throw new Error('Invalid catalogue');
    const coverage = coverageResponse && coverageResponse.ok ? await coverageResponse.json() : null;
    const values = [
      ['Imported records', books.length],
      ['With available copies', books.filter(b => b.available_copies > 0).length],
      ['With ratings', books.filter(b => b.openlibrary_rating_average > 0 && b.openlibrary_rating_count > 0).length],
      ['Recent releases', books.filter(b => b.is_recent_release === true).length],
      ['With descriptions', books.filter(b => typeof b.description === 'string' && b.description.trim()).length],
      ['With quality flags', books.filter(b => Array.isArray(b.quality_flags) && b.quality_flags.length).length],
      ['Availability older than 24h', books.filter(b => { const t = Date.parse(b.availability_checked_at); return !Number.isFinite(t) || Date.now()-t > 86400000; }).length]
    ];
    if (coverage) {
      values.push(
        ['Discovered catalogue titles', coverage.discovered],
        ['Successfully imported', coverage.imported],
        ['Pending ingestion', coverage.pending],
        ['Failed and awaiting retry', coverage.failed],
        ['Catalogue coverage', coverage.coverage_percent + '%']
      );
    }
    for (const [label, value] of values) {
      const dt = document.createElement('dt'), dd = document.createElement('dd');
      dt.textContent = label; dd.textContent = typeof value === 'number' ? value.toLocaleString() : value;
      metrics.append(dt, dd);
    }
    status.textContent = coverage ? 'Resumable ingestion coverage: ' + coverage.coverage_percent + '%. Published snapshot, not live stock.' : 'Published catalogue snapshot, not live stock. Run the importer to create coverage data.';
  } catch (error) { status.textContent = 'Could not load dashboard: ' + error.message; }
})();
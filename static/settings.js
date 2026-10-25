
  // 1. Dynamic Next Invoice ID Live Evaluator
  const prefixInput = document.getElementById('setting-prefix');
  const nextSeqInput = document.getElementById('setting-next-invoice');
  const digitsSelect = document.getElementById('setting-digits');
  const nextIdPreview = document.getElementById('next-id-preview');

  function updateNextIdPreview() {
    if (!prefixInput || !nextSeqInput || !digitsSelect || !nextIdPreview) return;
    try {
      const pattern = prefixInput.value || 'INV/{fy}/{seq}';
      const seqNum = parseInt(nextSeqInput.value, 10) || 1;
      const digits = parseInt(digitsSelect.value, 10) || 3;
      const paddedSeq = String(seqNum).padStart(digits, '0');

      // Approximate Indian FY (e.g. 26-27 or 24-25)
      const now = new Date();
      const currentYear = now.getFullYear();
      const startYear = (now.getMonth() >= 3) ? currentYear : currentYear - 1;
      const endYear = startYear + 1;
      const fyStr = String(startYear).slice(-2) + '-' + String(endYear).slice(-2);

      const previewStr = pattern.replace('{seq}', paddedSeq).replace('{fy}', fyStr);
      nextIdPreview.textContent = previewStr;
    } catch (e) {
      nextIdPreview.textContent = 'INV/26-27/001';
    }
  }

  if (prefixInput && nextSeqInput && digitsSelect) {
    prefixInput.addEventListener('input', updateNextIdPreview);
    nextSeqInput.addEventListener('input', updateNextIdPreview);
    digitsSelect.addEventListener('change', updateNextIdPreview);
    updateNextIdPreview();
  }

  // 2. Character counter for Terms & Conditions
  const termsInput = document.getElementById('setting-terms');
  const termsCounter = document.getElementById('terms-char-count');
  if (termsInput && termsCounter) {
    termsInput.addEventListener('input', () => {
      termsCounter.textContent = termsInput.value.length + ' characters';
    });
  }

  // 3. GST Tax Rate Chips Interactivity
  const gstInput = document.getElementById('setting-gst-rates');
  const rateChips = document.querySelectorAll('#rate-chips .stitch-rate-chip');
  if (gstInput && rateChips.length) {
    function syncRateChips(){
      const selected=gstInput.value.split(',').map(value=>value.trim());
      rateChips.forEach(chip=>{const active=selected.includes(chip.dataset.rate);chip.classList.toggle('active',active);chip.setAttribute('aria-pressed',String(active));});
    }
    syncRateChips();gstInput.addEventListener('input',syncRateChips);
    rateChips.forEach(chip => {
      chip.addEventListener('click', () => {
        const rate = chip.dataset.rate;
        const currentRates = gstInput.value.split(',').map(s => s.trim()).filter(Boolean);
        const selected=currentRates.includes(rate);
        const rates=selected?currentRates.filter(value=>value!==rate):[...currentRates,rate];
        rates.sort((a,b)=>parseFloat(a)-parseFloat(b));
        gstInput.value=rates.join(',');
        syncRateChips();
      });
    });
  }

  // 4. File Upload Previews
  const logoInput = document.getElementById('input-logo-file');
  const logoPreviewBox = document.getElementById('logo-preview-box');
  const logoFilename = document.getElementById('logo-filename');
  if (logoInput) {
    logoInput.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (file) {
        logoFilename.textContent = file.name + ' (' + Math.round(file.size / 1024) + ' KB)';
        const reader = new FileReader();
        reader.onload = (evt) => {
          logoPreviewBox.innerHTML = '<img src="' + evt.target.result + '" style="max-width:100%;max-height:100%;object-fit:contain;">';
        };
        reader.readAsDataURL(file);
      }
    });
  }

  const signInput = document.getElementById('input-sign-file');
  const signPreviewBox = document.getElementById('sign-preview-box');
  const signFilename = document.getElementById('sign-filename');
  if (signInput) {
    signInput.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (file) {
        signFilename.textContent = file.name + ' (' + Math.round(file.size / 1024) + ' KB)';
        const reader = new FileReader();
        reader.onload = (evt) => {
          signPreviewBox.innerHTML = '<img src="' + evt.target.result + '" style="max-width:100%;max-height:100%;object-fit:contain;">';
        };
        reader.readAsDataURL(file);
      }
    });
  }

  // 5. Audit Trail Real-time Filter
  const auditFilterInput = document.getElementById('audit-filter-input');
  const auditRows = document.querySelectorAll('#audit-table-body .audit-row');
  const auditShowingCount = document.getElementById('audit-showing-count');
  if (auditFilterInput && auditRows.length) {
    auditFilterInput.addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase().trim();
      let visible = 0;
      auditRows.forEach(row => {
        const text = row.dataset.search || row.textContent.toLowerCase();
        if (!q || text.includes(q)) {
          row.style.display = '';
          visible++;
        } else {
          row.style.display = 'none';
        }
      });
      if (auditShowingCount) {
        auditShowingCount.textContent = 'Showing ' + visible + ' of ' + auditRows.length + ' recorded system events';
      }
    });
  }

  // 6. Danger Zone Accordions
  const toggleSectionsBtn = document.getElementById('toggle-sections-reset-btn');
  const sectionsBox = document.getElementById('sections-reset-container');
  if (toggleSectionsBtn && sectionsBox) {
    toggleSectionsBtn.addEventListener('click', () => {
      const isHidden = sectionsBox.style.display === 'none';
      sectionsBox.style.display = isHidden ? 'flex' : 'none';
      toggleSectionsBtn.querySelector('span').textContent = isHidden ? 'Hide reset options' : 'Choose what to reset';
    });
  }

  const toggleCompanyBtn = document.getElementById('toggle-company-reset-btn');
  const companyBox = document.getElementById('company-reset-container');
  if (toggleCompanyBtn && companyBox) {
    toggleCompanyBtn.addEventListener('click', () => {
      const isHidden = companyBox.style.display === 'none';
      companyBox.style.display = isHidden ? 'flex' : 'none';
      toggleCompanyBtn.querySelector('span').textContent = isHidden ? 'Collapse Reset Controls' : 'Expand Reset Controls';
    });
  }

  // 7. Keyboard Shortcut (⌘S / Ctrl+S) to submit Settings Form
  window.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
      e.preventDefault();
      const settingsForm = document.getElementById('settings-form');
      if (settingsForm) {
        settingsForm.requestSubmit();
      }
    }
  });

  // 8. Sticky Nav Active Indicator on Scroll
  const navTabs = document.querySelectorAll('#settings-nav .stitch-settings-tab');
  const sections = document.querySelectorAll('.stitch-settings-card');
  window.addEventListener('scroll', () => {
    let currentId = '';
    sections.forEach(sec => {
      const rect = sec.getBoundingClientRect();
      if (rect.top <= 140 && rect.bottom >= 140) {
        currentId = sec.id;
      }
    });
    if (currentId) {
      navTabs.forEach(tab => {
        if (tab.getAttribute('href') === '#' + currentId) {
          tab.classList.add('active');
        } else if (!tab.classList.contains('stitch-settings-tab-danger')) {
          tab.classList.remove('active');
        }
      });
    }
  });

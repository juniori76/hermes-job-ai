
    function switchTab(tab) {
      ['vagas', 'copilot', 'regras', 'curriculo', 'sessoes', 'admin'].forEach(t => {
        const el = document.getElementById('content-' + t);
        const btn = document.getElementById('tab-' + t);
        if (t === tab) {
          el.classList.remove('hidden');
          btn.className = 'px-4 py-2 rounded-xl font-bold text-white bg-indigo-600 transition flex items-center gap-2 whitespace-nowrap';
        } else {
          el.classList.add('hidden');
          btn.className = 'px-4 py-2 rounded-xl font-medium text-slate-400 hover:text-white transition flex items-center gap-2 whitespace-nowrap';
        }
      });
    }

    async function triggerAction(endpoint, msg) {
      try {
        const res = await fetch(endpoint, { method: 'POST' });
        if (res.ok) {
          alert(msg);
          setTimeout(() => window.location.reload(), 2500);
        }
      } catch (e) {
        alert('Erro: ' + e);
      }
    }

    async function updateJobStatus(jobId, newStatus) {
      try {
        await fetch(`/api/jobs/${jobId}/status`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: newStatus })
        });
        window.location.reload();
      } catch (e) {
        alert('Erro: ' + e);
      }
    }

    async function saveAllJobRules() {
      const payload = {
        cidade: document.getElementById('regra-cidade').value,
        estado: document.getElementById('regra-estado').value,
        bairro: document.getElementById('regra-bairro').value,
        cargos: document.getElementById('regra-cargos').value,
        remoto_aceitar: document.getElementById('regra-remoto-aceitar').checked,
        hibrido_aceitar: document.getElementById('regra-hibrido-aceitar').checked,
        hibrido_km: document.getElementById('regra-hibrido-km').value,
        hibrido_dias: document.getElementById('regra-hibrido-dias').value,
        presencial_aceitar: document.getElementById('regra-presencial-aceitar').checked,
        presencial_km: document.getElementById('regra-presencial-km').value,
        salario_min_clt: document.getElementById('regra-salario-min-clt').value,
        pretensao_clt: document.getElementById('regra-pretensao-clt').value,
        salario_min_pj: document.getElementById('regra-salario-min-pj').value,
        pretensao_pj: document.getElementById('regra-pretensao-pj').value
      };

      try {
        const res = await fetch('/api/settings/profile', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        if (res.ok) {
          alert('Todas as regras de modalidade, raio em km e salários foram salvas com sucesso!');
          window.location.reload();
        }
      } catch (e) {
        alert('Erro ao salvar: ' + e);
      }
    }

    async function uploadResumeFile() {
      const file = document.getElementById('resume-file-input').files[0];
      if (!file) return alert('Selecione um PDF.');
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch('/api/settings/upload-resume', { method: 'POST', body: fd });
      if (res.ok) { 
        alert('Currículo enviado com sucesso! Clique em "Sincronizar Perfil com IA" para ler os novos dados.'); 
        window.location.reload(); 
      }
    }

    async function triggerProfileSync() {
      if (!confirm('Deseja que a IA extraia todas as competências e experiências do PDF e atualize seu perfil?')) return;
      document.getElementById('resume-loading').classList.remove('hidden');
      document.getElementById('resume-report').classList.add('hidden');
      try {
        const res = await fetch('/api/profile/sync', { method: 'POST' });
        const data = await res.json();
        document.getElementById('resume-loading').classList.add('hidden');
        document.getElementById('resume-report').classList.remove('hidden');
        if (data.status === 'success') {
          alert('Perfil sincronizado com sucesso a partir do seu PDF!');
          window.location.reload();
        } else {
          alert('Aviso: ' + data.message);
        }
      } catch (e) {
        document.getElementById('resume-loading').classList.add('hidden');
        document.getElementById('resume-report').classList.remove('hidden');
        alert('Erro ao sincronizar perfil: ' + e);
      }
    }

        async function applyJob(jobId) {
      if (!confirm('Deseja iniciar a candidatura automática real via Playwright para esta vaga? O robô preencherá o formulário e anexará seu currículo.')) return;
      showToast('🚀 Iniciando candidatura automática via Playwright...', 'green');
      try {
        const res = await fetch(`/api/jobs/${jobId}/apply`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          showToast('✅ Candidatura em execução em background!', 'green');
        } else {
          alert('Aviso: ' + (data.message || data.error));
        }
      } catch (e) {
        alert('Erro ao disparar candidatura: ' + e);
      }
    }

    async function dryRunJob(jobId) {
      showToast('🧪 Iniciando simulação (preencher + screenshot sem enviar)...', 'purple');
      try {
        const res = await fetch(`/api/jobs/${jobId}/dry-run`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          showToast('📸 Simulação rodando! O print será salvo em data/screenshots.', 'purple');
        }
      } catch (e) {
        alert('Erro ao disparar simulação: ' + e);
      }
    }

async function changePassword() {
      const p = document.getElementById('new-password-input').value.trim();
      if (!p || p.length < 6) return alert('Digite uma senha com no mínimo 6 caracteres.');
      const res = await fetch('/api/auth/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_password: p })
      });
      if (res.ok) {
        alert('Senha alterada com sucesso! Guarde sua nova senha.');
        document.getElementById('new-password-input').value = '';
      } else {
        alert('Erro ao alterar senha.');
      }
    }

    async function fetchResumeDiagnostic() {
      document.getElementById('resume-loading').classList.remove('hidden');
      document.getElementById('resume-report').classList.add('hidden');
      try {
        const res = await fetch('/api/resume/analysis');
        const data = await res.json();
        document.getElementById('resume-loading').classList.add('hidden');
        document.getElementById('resume-report').classList.remove('hidden');
        window.location.reload();
      } catch (e) {
        document.getElementById('resume-loading').classList.add('hidden');
        document.getElementById('resume-report').classList.remove('hidden');
        alert('Erro ao consultar IA: ' + e);
      }
    }

    // ======================================================
    // FASE 4 — Modo de Operação & Telegram
    // ======================================================

    const MODE_INFO = {
      review: {
        label: '🔵 Modo Avaliação',
        desc: 'O Hermes apenas monitora e classifica vagas. Você decide tudo manualmente. Nenhuma ação automática é realizada.',
        boxClass: 'bg-blue-500/10 text-blue-300 border border-blue-500/20',
        btnActive: 'border-blue-500 bg-blue-500/20 text-blue-300',
        btnInactive: 'border-slate-700 bg-transparent text-slate-400'
      },
      smart: {
        label: '🟣 Modo Inteligente',
        desc: 'O Hermes envia alertas via Telegram quando encontra vagas com score alto (≥80%). Você aprova ou rejeita pelo chat. A candidatura só é enviada com sua aprovação.',
        boxClass: 'bg-purple-500/10 text-purple-300 border border-purple-500/20',
        btnActive: 'border-purple-500 bg-purple-500/20 text-purple-300',
        btnInactive: 'border-slate-700 bg-transparent text-slate-400'
      },
      auto: {
        label: '🟢 Modo Automático',
        desc: 'O Hermes monitora, alerta via Telegram E se candidata automaticamente nas vagas com score ≥85%. Você é notificado de cada candidatura. Respeita o limite diário configurado.',
        boxClass: 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/20',
        btnActive: 'border-emerald-500 bg-emerald-500/20 text-emerald-300',
        btnInactive: 'border-slate-700 bg-transparent text-slate-400'
      }
    };

    let currentMode = 'review';

    async function loadCurrentSettings() {
      try {
        const res = await fetch('/api/settings');
        const s = await res.json();
        currentMode = s.operation_mode || 'review';
        applyModeUI(currentMode);

        // Thresholds
        if (document.getElementById('thresh-smart')) {
          document.getElementById('thresh-smart').value = s.smart_score_threshold || 80;
          document.getElementById('thresh-auto').value = s.auto_score_threshold || 85;
          document.getElementById('thresh-daily').value = s.auto_apply_daily_limit || 10;
        }

        // Status badge Telegram
        const badge = document.getElementById('tg-status-badge');
        if (badge) {
          if (s.telegram_enabled) {
            badge.textContent = '✅ Configurado';
            badge.className = 'text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-sky-500/10 text-sky-400 border border-sky-500/30';
          } else {
            badge.textContent = 'Não configurado';
            badge.className = 'text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700';
          }
          if (s.telegram_chat_id) {
            document.getElementById('tg-chatid-input').value = s.telegram_chat_id;
          }
        }
      } catch(e) { console.warn('Erro ao carregar settings:', e); }
    }

    function applyModeUI(mode) {
      const info = MODE_INFO[mode] || MODE_INFO['review'];
      // Atualiza botões
      ['review', 'smart', 'auto'].forEach(m => {
        const btn = document.getElementById('btn-mode-' + m);
        if (!btn) return;
        const modeInfo = MODE_INFO[m];
        if (m === mode) {
          btn.className = `mode-btn px-5 py-2.5 rounded-2xl text-sm font-bold border-2 transition flex items-center gap-2 ${modeInfo.btnActive}`;
        } else {
          btn.className = `mode-btn px-5 py-2.5 rounded-2xl text-sm font-bold border-2 transition flex items-center gap-2 ${modeInfo.btnInactive} hover:text-white`;
        }
      });
      // Atualiza caixa de info
      const box = document.getElementById('mode-info-box');
      if (box) {
        box.className = `mt-3 p-3 rounded-xl text-xs ${info.boxClass}`;
        box.innerHTML = `<strong>${info.label}:</strong> ${info.desc}`;
        box.style.display = 'block';
      }
      // Atualiza descrição curta
      const desc = document.getElementById('mode-description');
      if (desc) desc.textContent = info.desc.substring(0, 80) + '…';
    }

    async function setOperationMode(mode) {
      try {
        const res = await fetch('/api/settings/mode', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode })
        });
        const data = await res.json();
        if (data.success) {
          currentMode = mode;
          applyModeUI(mode);
          const labels = { review: 'Avaliação', smart: 'Inteligente', auto: 'Automático' };
          // Toast simples
          showToast(`✅ Modo alterado para ${labels[mode]}`, mode === 'review' ? 'blue' : mode === 'smart' ? 'purple' : 'green');
        }
      } catch(e) { alert('Erro ao salvar modo: ' + e); }
    }

    async function saveTelegramConfig() {
      const token = document.getElementById('tg-token-input').value.trim();
      const chat_id = document.getElementById('tg-chatid-input').value.trim();
      if (!token || !chat_id) return alert('Preencha o Token e o Chat ID.');
      const res = await fetch('/api/settings/telegram', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, chat_id })
      });
      const data = await res.json();
      if (data.success) {
        showToast('✅ Telegram salvo com sucesso!', 'sky');
        loadCurrentSettings();
      } else {
        alert('Erro ao salvar Telegram: ' + JSON.stringify(data));
      }
    }

    async function testTelegramConnection() {
      const token = document.getElementById('tg-token-input').value.trim();
      const chat_id = document.getElementById('tg-chatid-input').value.trim();
      if (!token || !chat_id) return alert('Preencha o Token e o Chat ID antes de testar.');
      showToast('⏳ Enviando mensagem de teste…', 'slate');
      const res = await fetch('/api/settings/telegram/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, chat_id })
      });
      const data = await res.json();
      if (data.success) {
        showToast('📱 Mensagem enviada! Verifique seu Telegram.', 'sky');
      } else {
        alert('❌ Falha no Telegram:\n' + data.message);
      }
    }

    async function saveThresholds() {
      const payload = {
        smart_score_threshold: parseInt(document.getElementById('thresh-smart').value),
        auto_score_threshold: parseInt(document.getElementById('thresh-auto').value),
        auto_apply_daily_limit: parseInt(document.getElementById('thresh-daily').value)
      };
      const res = await fetch('/api/settings/thresholds', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data.success) showToast('✅ Thresholds salvos!', 'indigo');
    }

    // Toast notification helper
    function showToast(msg, color = 'indigo') {
      const colorMap = {
        indigo: 'bg-indigo-600 text-white', blue: 'bg-blue-600 text-white',
        purple: 'bg-purple-600 text-white', green: 'bg-emerald-600 text-white',
        sky: 'bg-sky-600 text-white', slate: 'bg-slate-700 text-white'
      };
      const toast = document.createElement('div');
      toast.className = `fixed bottom-6 right-6 z-50 px-5 py-3 rounded-2xl font-bold text-sm shadow-2xl transition-all ${colorMap[color] || colorMap.indigo}`;
      toast.textContent = msg;
      document.body.appendChild(toast);
      setTimeout(() => toast.remove(), 3500);
    }

    // Carrega settings ao iniciar a página
    document.addEventListener('DOMContentLoaded', () => { loadCurrentSettings(); checkAuthStatusNow(); setInterval(checkAuthStatusNow, 6000); });

    async function checkAuthStatusNow() {
      const elIn = document.getElementById('status-linkedin');
      const elGu = document.getElementById('status-gupy');
      const btnIn = document.getElementById('btn-login-linkedin');
      const btnGu = document.getElementById('btn-login-gupy');
      try {
        const res = await fetch('/api/auth/browser-status');
        const data = await res.json();
        if (elIn) {
          elIn.innerHTML = data.linkedin ? '<span class="text-emerald-400 font-bold flex items-center gap-1"><i class="fa-solid fa-circle-check"></i> Conectado (Sessão Ativa)</span>' : '<span class="text-rose-400 font-bold flex items-center gap-1"><i class="fa-solid fa-circle-xmark"></i> Desconectado</span>';
        }
        if (btnIn) {
          if (data.linkedin) {
            btnIn.className = 'bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 text-xs font-bold px-3.5 py-2 rounded-xl transition flex items-center gap-1.5';
            btnIn.innerHTML = '<i class="fa-solid fa-check"></i> Conectado';
          } else {
            btnIn.className = 'bg-sky-600 hover:bg-sky-500 text-white text-xs font-bold px-3.5 py-2 rounded-xl transition flex items-center gap-1.5';
            btnIn.innerHTML = '<i class="fa-solid fa-arrow-up-right-from-square"></i> Logar';
          }
        }
        if (elGu) {
          elGu.innerHTML = data.gupy ? '<span class="text-emerald-400 font-bold flex items-center gap-1"><i class="fa-solid fa-circle-check"></i> Conectado (Sessão Ativa)</span>' : '<span class="text-rose-400 font-bold flex items-center gap-1"><i class="fa-solid fa-circle-xmark"></i> Desconectado</span>';
        }
        if (btnGu) {
          if (data.gupy) {
            btnGu.className = 'bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 text-xs font-bold px-3.5 py-2 rounded-xl transition flex items-center gap-1.5';
            btnGu.innerHTML = '<i class="fa-solid fa-check"></i> Conectado';
          } else {
            btnGu.className = 'bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold px-3.5 py-2 rounded-xl transition flex items-center gap-1.5';
            btnGu.innerHTML = '<i class="fa-solid fa-arrow-up-right-from-square"></i> Logar';
          }
        }
      } catch (e) {
        if (elIn && !elIn.innerHTML.includes('Conectado')) elIn.textContent = 'Erro ao verificar';
        if (elGu && !elGu.innerHTML.includes('Conectado')) elGu.textContent = 'Erro ao verificar';
      }
    }
    async function startAssistedLogin(platform) {
      showToast('🌐 Abrindo navegador para login assistido...', 'sky');
      toggleVncFrame(true);
      try {
        await fetch(`/api/auth/assisted-login?platform=${platform}`, { method: 'POST' });
      } catch (e) {
        console.warn('Login assistido disparado');
      }
    }

    function toggleVncFrame(forceOpen = false) {
      const container = document.getElementById('vnc-container');
      const frame = document.getElementById('vnc-frame');
      const btn = document.getElementById('btn-toggle-vnc');
      if (!container || !frame) return;
      const isOpen = !container.classList.contains('hidden');
      if (isOpen && !forceOpen) {
        container.classList.add('hidden');
        frame.src = '';
        btn.textContent = 'Abrir Visualizador no Painel';
      } else {
        container.classList.remove('hidden');
        frame.src = 'http://192.168.0.123:6080/vnc.html?autoconnect=true&resize=remote';
        btn.textContent = 'Recolher Visualizador';
      }
    }


  
    // ==========================================
    // COPILOTO IA VISUAL (CTRL+V / PRINTS)
    // ==========================================
    let copilotCurrentBase64 = null;

    // Escuta evento global de Paste (Ctrl+V)
    window.addEventListener('paste', function(e) {
      // Se não houver itens na área de transferência, ignora
      if (!e.clipboardData || !e.clipboardData.items) return;
      
      for (let item of e.clipboardData.items) {
        if (item.type.indexOf('image') !== -1) {
          const blob = item.getAsFile();
          const reader = new FileReader();
          reader.onload = function(event) {
            setCopilotImage(event.target.result);
            // Muda para a aba do Copiloto automaticamente para facilitar!
            switchTab('copilot');
          };
          reader.readAsDataURL(blob);
          break;
        }
      }
    });

    function setCopilotImage(dataUrl) {
      copilotCurrentBase64 = dataUrl;
      const previewImg = document.getElementById('copilot-preview-img');
      const emptyState = document.getElementById('dropzone-empty-state');
      const previewState = document.getElementById('dropzone-preview-state');
      
      previewImg.src = dataUrl;
      emptyState.classList.add('hidden');
      previewState.classList.remove('hidden');
    }

    function clearCopilotImage(event) {
      if (event) event.stopPropagation();
      copilotCurrentBase64 = null;
      document.getElementById('copilot-file-input').value = '';
      document.getElementById('dropzone-empty-state').classList.remove('hidden');
      document.getElementById('dropzone-preview-state').classList.add('hidden');
    }

    function handleCopilotFileSelect(e) {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = function(event) {
        setCopilotImage(event.target.result);
      };
      reader.readAsDataURL(file);
    }

    async function submitCopilotQuestion() {
      const username = document.getElementById('copilot-profile').value;
      const textQuestion = document.getElementById('copilot-text').value;
      
      if (!copilotCurrentBase64 && (!textQuestion || !textQuestion.trim())) {
        alert("Por favor, cole um print da tela (Ctrl + V) ou digite a pergunta antes de enviar.");
        return;
      }

      const emptyEl = document.getElementById('copilot-empty-result');
      const loadingEl = document.getElementById('copilot-loading');
      const containerEl = document.getElementById('copilot-answer-container');
      const textEl = document.getElementById('copilot-answer-text');
      const copyBtn = document.getElementById('copilot-copy-btn');
      const submitBtn = document.getElementById('copilot-submit-btn');

      emptyEl.classList.add('hidden');
      containerEl.classList.add('hidden');
      copyBtn.classList.add('hidden');
      loadingEl.classList.remove('hidden');
      submitBtn.disabled = true;
      submitBtn.classList.add('opacity-50');

      try {
        const payload = {
          username: username,
          text_question: textQuestion || null,
          image_base64: copilotCurrentBase64 || null
        };

        const res = await fetch('/api/copilot/answer', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        const data = await res.json();
        loadingEl.classList.add('hidden');
        submitBtn.disabled = false;
        submitBtn.classList.remove('opacity-50');

        if (data.success) {
          textEl.textContent = data.copy_text || data.answer_markdown;
          containerEl.classList.remove('hidden');
          copyBtn.classList.remove('hidden');
        } else {
          emptyEl.classList.remove('hidden');
          alert("Erro: " + (data.error || "Não foi possível gerar a resposta."));
        }
      } catch (err) {
        loadingEl.classList.add('hidden');
        emptyEl.classList.remove('hidden');
        submitBtn.disabled = false;
        submitBtn.classList.remove('opacity-50');
        alert("Erro na conexão com o servidor: " + err.message);
      }
    }

    function copyCopilotAnswer() {
      const textEl = document.getElementById('copilot-answer-text');
      const copyBtn = document.getElementById('copilot-copy-btn');
      if (!textEl || !textEl.textContent) return;

      navigator.clipboard.writeText(textEl.textContent).then(() => {
        const originalHtml = copyBtn.innerHTML;
        copyBtn.innerHTML = '<i class="fa-solid fa-check"></i> Copiado!';
        copyBtn.classList.remove('bg-emerald-600', 'hover:bg-emerald-500');
        copyBtn.classList.add('bg-indigo-600');
        setTimeout(() => {
          copyBtn.innerHTML = originalHtml;
          copyBtn.classList.remove('bg-indigo-600');
          copyBtn.classList.add('bg-emerald-600', 'hover:bg-emerald-500');
        }, 2500);
      }).catch(err => {
        alert("Erro ao copiar para a área de transferência: " + err);
      });
    }

  
    // ==========================================
    // GESTÃO ADMINISTRATIVA DE PERFIS E LOGINS
    // ==========================================
    let cachedAdminProfiles = [];

    async function loadAdminProfiles() {
      const grid = document.getElementById('admin-profiles-grid');
      try {
        const res = await fetch('/api/admin/profiles-full');
        const data = await res.json();
        cachedAdminProfiles = data.profiles || [];
        renderAdminProfiles(cachedAdminProfiles);
      } catch (err) {
        grid.innerHTML = `<div class="col-span-full text-center text-red-400 py-6">Erro ao carregar perfis: ${err.message}</div>`;
      }
    }

    function renderAdminProfiles(profiles) {
      const grid = document.getElementById('admin-profiles-grid');
      if (!profiles || profiles.length === 0) {
        grid.innerHTML = '<div class="col-span-full text-center text-slate-500 py-6">Nenhum perfil cadastrado.</div>';
        return;
      }

      grid.innerHTML = profiles.map(p => {
        const isMaster = p.id === 'eduardo';
        const rolesList = (p.cargos_alvo || []).map(r => `<span class="px-2 py-0.5 rounded-md bg-slate-800 text-slate-300 text-xs border border-slate-700">${r}</span>`).join(' ');
        
        return `
          <div class="bg-slate-950/80 border border-slate-800 rounded-2xl p-5 hover:border-slate-700 transition flex flex-col justify-between shadow-xl">
            <div>
              <div class="flex items-start justify-between gap-3 mb-3">
                <div class="flex items-center gap-3">
                  <div class="w-12 h-12 rounded-2xl ${isMaster ? 'bg-indigo-600/20 text-indigo-400 border border-indigo-500/30' : 'bg-purple-600/20 text-purple-400 border border-purple-500/30'} flex items-center justify-center text-xl font-black">
                    ${isMaster ? '<i class="fa-solid fa-crown"></i>' : '<i class="fa-solid fa-user"></i>'}
                  </div>
                  <div>
                    <h3 class="font-bold text-white text-base">${p.display_name}</h3>
                    <div class="flex items-center gap-2 text-xs text-slate-400">
                      <span>Login: <code class="text-purple-300 font-mono">@${p.id}</code></span>
                      ${isMaster ? '<span class="px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 text-[10px] font-bold">ADMIN MASTER</span>' : ''}
                    </div>
                  </div>
                </div>

                <div>
                  ${p.has_resume 
                    ? '<span class="px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-semibold flex items-center gap-1"><i class="fa-solid fa-file-pdf"></i> Currículo OK</span>'
                    : '<span class="px-2.5 py-1 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs font-semibold flex items-center gap-1"><i class="fa-solid fa-triangle-exclamation"></i> Sem Currículo</span>'
                  }
                </div>
              </div>

              <!-- DADOS DO PERFIL -->
              <div class="space-y-2 text-xs text-slate-400 my-4 bg-slate-900/60 p-3 rounded-xl border border-slate-800/80">
                <div class="flex justify-between">
                  <span>Localização:</span>
                  <strong class="text-slate-200">${p.cidade || 'Diadema'}, ${p.estado || 'SP'} (Raio: ${p.distancia_km || 30}km)</strong>
                </div>
                <div class="flex justify-between">
                  <span>Salário Mínimo:</span>
                  <strong class="text-emerald-400">R$ ${(p.salario_min || 3000).toLocaleString('pt-BR')}</strong>
                </div>
                ${p.email ? `<div class="flex justify-between"><span>E-mail:</span><strong class="text-slate-200">${p.email}</strong></div>` : ''}
              </div>

              <!-- CARGOS PRETENDIDOS -->
              <div class="mb-4">
                <span class="text-[11px] font-bold uppercase tracking-wider text-slate-500 block mb-1.5">Cargos de Interesse:</span>
                <div class="flex flex-wrap gap-1.5">
                  ${rolesList || '<span class="text-xs text-slate-500">Nenhum cargo definido</span>'}
                </div>
              </div>
            </div>

            <!-- BOTÕES DE AÇÃO -->
            <div class="pt-3 border-t border-slate-800/80 flex items-center justify-between gap-2">
              <div class="flex items-center gap-2">
                <button 
                  onclick="openEditProfileModal('${p.id}')" 
                  class="px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-200 text-xs font-bold transition flex items-center gap-1.5"
                >
                  <i class="fa-solid fa-pen-to-square"></i> Editar
                </button>

                <!-- BOTÃO UPLOAD CURRÍCULO -->
                <label class="px-3 py-1.5 rounded-xl bg-indigo-600/20 hover:bg-indigo-600/30 border border-indigo-500/30 text-indigo-300 hover:text-white text-xs font-bold cursor-pointer transition flex items-center gap-1.5">
                  <i class="fa-solid fa-upload"></i> Subir PDF
                  <input type="file" accept=".pdf" class="hidden" onchange="uploadResumeForUser(event, '${p.id}')">
                </label>
              </div>

              ${!isMaster ? `
                <button 
                  onclick="deleteUserAccount('${p.id}')" 
                  class="px-2.5 py-1.5 rounded-xl text-red-400 hover:text-red-300 hover:bg-red-500/10 transition text-xs font-bold"
                  title="Excluir Perfil"
                >
                  <i class="fa-regular fa-trash-can"></i>
                </button>
              ` : ''}
            </div>
          </div>
        `;
      }).join('');
    }

    // Modal Criar Usuário
    function openCreateUserModal() {
      document.getElementById('modal-create-user').classList.remove('hidden');
    }
    function closeCreateUserModal() {
      document.getElementById('modal-create-user').classList.add('hidden');
    }
    async function submitCreateUser(e) {
      e.preventDefault();
      const payload = {
        display_name: document.getElementById('new-user-fullname').value,
        username: document.getElementById('new-user-login').value,
        password: document.getElementById('new-user-pass').value,
        cargos_alvo: document.getElementById('new-user-roles').value,
        cidade: document.getElementById('new-user-city').value,
        distancia_km: parseInt(document.getElementById('new-user-km').value) || 30
      };

      try {
        const res = await fetch('/api/admin/users/create', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
          closeCreateUserModal();
          alert("Perfil criado com sucesso!");
          loadAdminProfiles();
        } else {
          alert("Erro: " + (data.error || "Falha ao criar usuário"));
        }
      } catch (err) {
        alert("Erro de conexão: " + err.message);
      }
    }

    // Modal Editar Perfil
    function openEditProfileModal(userId) {
      const p = cachedAdminProfiles.find(x => x.id === userId);
      if (!p) return;

      document.getElementById('edit-user-id').value = p.id;
      document.getElementById('edit-user-fullname').value = p.display_name || '';
      document.getElementById('edit-user-email').value = p.email || '';
      document.getElementById('edit-user-phone').value = p.telefone || '';
      document.getElementById('edit-user-roles').value = (p.cargos_alvo || []).join(', ');
      document.getElementById('edit-user-city').value = p.cidade || 'Diadema';
      document.getElementById('edit-user-salary').value = p.salario_min || 3000;
      document.getElementById('edit-user-km').value = p.distancia_km || 30;
      document.getElementById('edit-user-linkedin').value = p.linkedin_url || '';

      document.getElementById('modal-edit-profile').classList.remove('hidden');
    }
    function closeEditProfileModal() {
      document.getElementById('modal-edit-profile').classList.add('hidden');
    }
    async function submitEditProfile(e) {
      e.preventDefault();
      const userId = document.getElementById('edit-user-id').value;
      const payload = {
        username: userId,
        nome_completo: document.getElementById('edit-user-fullname').value,
        email: document.getElementById('edit-user-email').value,
        telefone: document.getElementById('edit-user-phone').value,
        cargos_alvo: document.getElementById('edit-user-roles').value,
        cidade: document.getElementById('edit-user-city').value,
        salario_min: parseFloat(document.getElementById('edit-user-salary').value) || 3000,
        distancia_km: parseInt(document.getElementById('edit-user-km').value) || 30,
        linkedin_url: document.getElementById('edit-user-linkedin').value
      };

      try {
        const res = await fetch('/api/admin/profiles/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
          closeEditProfileModal();
          alert("Perfil atualizado com sucesso!");
          loadAdminProfiles();
        } else {
          alert("Erro: " + (data.error || "Falha ao salvar dados"));
        }
      } catch (err) {
        alert("Erro de conexão: " + err.message);
      }
    }

    // Upload de Currículo PDF para Perfil Específico
    async function uploadResumeForUser(e, userId) {
      const file = e.target.files[0];
      if (!file) return;

      const formData = new FormData();
      formData.append('username', userId);
      formData.append('file', file);

      try {
        const res = await fetch('/api/admin/profiles/upload-resume', {
          method: 'POST',
          body: formData
        });
        const data = await res.json();
        if (data.success) {
          alert(`Currículo de ${userId} enviado com sucesso!`);
          loadAdminProfiles();
        } else {
          alert("Erro ao enviar: " + (data.error || "Formato inválido"));
        }
      } catch (err) {
        alert("Erro de conexão: " + err.message);
      }
    }

    // Excluir Perfil
    async function deleteUserAccount(userId) {
      if (!confirm(`Deseja realmente excluir o perfil de @${userId}?`)) return;

      try {
        const res = await fetch('/api/admin/users/delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: userId })
        });
        const data = await res.json();
        if (data.success) {
          alert("Perfil excluído com sucesso.");
          loadAdminProfiles();
        } else {
          alert("Erro: " + (data.error || "Não foi possível excluir"));
        }
      } catch (err) {
        alert("Erro de conexão: " + err.message);
      }
    }

    // Ao mudar para a aba admin, carrega automaticamente os perfis
    const originalSwitchTab = window.switchTab;
    window.switchTab = function(tab) {
      originalSwitchTab(tab);
      if (tab === 'admin') {
        loadAdminProfiles();
      }
    };

  
    // ==========================================
    // SISTEMA DE FILTRAGEM DINÂMICA DE VAGAS
    // ==========================================
    function applyAllJobFilters() {
      const search = (document.getElementById('filter-search')?.value || '').toLowerCase().trim();
      const scoreFilter = document.getElementById('filter-score')?.value || 'approved';
      const recencyFilter = document.getElementById('filter-recency')?.value || 'all';
      const modalityFilter = document.getElementById('filter-modality')?.value || 'all';
      const platformFilter = document.getElementById('filter-platform')?.value || 'all';

      const cards = document.querySelectorAll('.job-card');
      let visibleCount = 0;

      cards.forEach(card => {
        const title = card.getAttribute('data-title') || '';
        const company = card.getAttribute('data-company') || '';
        const location = card.getAttribute('data-location') || '';
        const keywords = card.getAttribute('data-keywords') || '';
        const score = parseFloat(card.getAttribute('data-score')) || -1;
        const status = card.getAttribute('data-status') || '';
        const ageHours = parseFloat(card.getAttribute('data-age-hours')) || 9999;
        const isRemote = card.getAttribute('data-remote') === '1';
        const platform = card.getAttribute('data-platform') || '';

        // 1. Busca por Texto
        let matchSearch = true;
        if (search) {
          matchSearch = title.includes(search) || company.includes(search) || location.includes(search) || keywords.includes(search);
        }

        // 2. Filtro de Score / Status
        let matchScore = true;
        if (scoreFilter === 'approved') {
          matchScore = (score >= 75) || (status === 'approve' || status === 'approved');
        } else if (scoreFilter === 'top') {
          matchScore = score >= 85;
        } else if (scoreFilter === 'pending') {
          matchScore = (score < 0 || status === 'discovered');
        } else if (scoreFilter === 'applied') {
          matchScore = (status === 'applied' || status === 'success');
        } else if (scoreFilter === 'dry_run') {
          matchScore = (status === 'dry_run');
        } else if (scoreFilter === 'rejected') {
          matchScore = (status === 'reject' || status === 'rejected');
        }

        // 3. Filtro de Recência
        let matchRecency = true;
        if (recencyFilter === '2h') matchRecency = ageHours <= 2;
        else if (recencyFilter === '6h') matchRecency = ageHours <= 6;
        else if (recencyFilter === '24h') matchRecency = ageHours <= 24;
        else if (recencyFilter === '3d') matchRecency = ageHours <= 72;
        else if (recencyFilter === '7d') matchRecency = ageHours <= 168;

        // 4. Modalidade
        let matchModality = true;
        if (modalityFilter === 'remote') matchModality = isRemote;
        else if (modalityFilter === 'presential') matchModality = !isRemote;

        // 5. Plataforma
        let matchPlatform = true;
        if (platformFilter !== 'all') {
          matchPlatform = platform.includes(platformFilter);
        }

        if (matchSearch && matchScore && matchRecency && matchModality && matchPlatform) {
          card.style.display = '';
          visibleCount++;
        } else {
          card.style.display = 'none';
        }
      });

      const countEl = document.getElementById('filtered-count');
      if (countEl) countEl.textContent = visibleCount;
      updatePillsVisual(scoreFilter);
    }

    function setScorePill(val) {
      const sel = document.getElementById('filter-score');
      if (sel) {
        sel.value = val;
        applyAllJobFilters();
      }
    }

    function updatePillsVisual(currentVal) {
      ['approved', 'top', 'pending', 'all'].forEach(k => {
        const p = document.getElementById('pill-' + k);
        if (!p) return;
        if (k === currentVal) {
          p.className = 'px-3.5 py-2 rounded-xl text-xs font-bold bg-indigo-600 text-white shadow-md shadow-indigo-600/30 transition flex items-center gap-1.5';
        } else {
          p.className = 'px-3.5 py-2 rounded-xl text-xs font-medium bg-slate-900 text-slate-400 border border-slate-800 hover:text-white transition flex items-center gap-1.5';
        }
      });
    }

    function filterFromMetric(type) {
      const scoreSelect = document.getElementById('filter-score');
      if (type === 'all') scoreSelect.value = 'all';
      else if (type === 'approved') scoreSelect.value = 'approved';
      else if (type === 'applied') scoreSelect.value = 'applied';
      applyAllJobFilters();
    }

    function resetJobFilters() {
      document.getElementById('filter-search').value = '';
      document.getElementById('filter-score').value = 'approved';
      document.getElementById('filter-recency').value = 'all';
      document.getElementById('filter-modality').value = 'all';
      document.getElementById('filter-platform').value = 'all';
      applyAllJobFilters();
    }

    async function cleanRejectedJobs() {
      if (!confirm("Deseja realmente apagar do banco de dados todas as vagas descartadas pela IA?")) return;
      try {
        const res = await fetch('/api/jobs/clean-rejected', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          alert(data.message);
          window.location.reload();
        } else {
          alert("Erro: " + (data.error || "Falha ao limpar"));
        }
      } catch (err) {
        alert("Erro de conexão: " + err.message);
      }
    }

    // Inicializa o filtro imediatamente ao carregar a página
    document.addEventListener('DOMContentLoaded', function() {
      applyAllJobFilters();
    });

  
    // ==========================================
    // AÇÕES RÁPIDAS DE FILA (CANDIDATAR & DESCARTAR)
    // ==========================================
    async function markAsApplied(jobId) {
      const card = document.querySelector(`[data-job-id="${jobId}"]`);
      try {
        const res = await fetch(`/api/jobs/${jobId}/status`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: 'applied' })
        });
        if (res.ok) {
          if (card) {
            card.setAttribute('data-status', 'applied');
            card.style.transition = 'all 0.35s ease';
            card.style.opacity = '0';
            card.style.transform = 'translateX(40px)';
            setTimeout(() => {
              card.remove();
              applyAllJobFilters();
            }, 350);
          }
          showToast('✅ Vaga marcada como candidatada com sucesso!', 'green');

          // Incrementa contador de candidaturas realizadas
          const metricEls = document.querySelectorAll('.glass-card p.text-3xl');
          if (metricEls && metricEls.length >= 3) {
            const cur = parseInt(metricEls[2].textContent.trim()) || 0;
            metricEls[2].textContent = cur + 1;
          }
        }
      } catch (err) {
        alert("Erro ao registrar candidatura: " + err.message);
      }
    }

    async function markAsDiscarded(jobId) {
      const card = document.querySelector(`[data-job-id="${jobId}"]`);
      try {
        const res = await fetch(`/api/jobs/${jobId}/status`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: 'rejected' })
        });
        if (res.ok) {
          if (card) {
            card.setAttribute('data-status', 'rejected');
            card.style.transition = 'all 0.35s ease';
            card.style.opacity = '0';
            card.style.transform = 'translateX(-40px)';
            setTimeout(() => {
              card.remove();
              applyAllJobFilters();
            }, 350);
          }
          showToast('🗑️ Vaga descartada da fila!', 'slate');
        }
      } catch (err) {
        alert("Erro ao descartar vaga: " + err.message);
      }
    }

  

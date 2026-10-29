(() => {
  'use strict';
  const data = JSON.parse(document.getElementById('code-board-data').textContent);
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const el = (tag, className, text) => { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; };
  const icons = {
    file:'<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M11.5 2.5H5a1 1 0 0 0-1 1v13a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-9l-4.5-5Z" stroke="currentColor" stroke-width="1.2"/><path d="M11 2.5v5h5M7 11h6M7 14h4" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg>',
    arrow:'<svg viewBox="0 0 12 12" fill="none" aria-hidden="true" class="source-open-icon"><path d="M3 9 9 3M3 3h6v6" stroke="currentColor" stroke-width="1.2"/></svg>',
    copy:'<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><rect x="6" y="6" width="10" height="11" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M12 6V3H3v10h3" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>',
    check:'<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="m4 10 4 4 8-8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    chevron:'<svg viewBox="0 0 12 12" fill="none" aria-hidden="true" class="gap-chevron"><path d="m3 4.5 3 3 3-3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    note:'<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.3"/><path d="M10 9v5m0-8v.3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
    question:'<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M7 7a3 3 0 0 1 6 0c0 2-3 2-3 4m0 3v.2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><circle cx="10" cy="10" r="8" stroke="currentColor" stroke-width="1.2"/></svg>',
    tip:'<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M7 14h6m-5 3h4M7 12C3 8 6 3 10 3s7 5 3 9v2H7v-2Z" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>'
  };
  const sources = new Map((data.sources || []).map(source => [source.id, source]));
  const steps = data.steps || [];
  const stepDomId = id => `code-board-step--${id}`;
  let currentIndex = -1;
  let toastTimer;
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  document.documentElement.lang = data.language || 'zh-CN';
  document.title = data.title || '代码讲解';
  $('#tutorial-title').textContent = data.title || '代码讲解';
  $('#tutorial-subtitle').textContent = data.subtitle || '';
  $('#tutorial-intro').innerHTML = data.intro_html || '';
  $('#draft-badge').hidden = !data.draft;
  $('#draft-badge').textContent = data.mode === 'draft' ? '草案' : '草稿';
  function toast(text) {
    const node = $('#toast');
    node.textContent = text;
    node.classList.add('visible');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => node.classList.remove('visible'), 2300);
  }

  function jumpToStep(id) {
    const target = document.getElementById(stepDomId(id));
    if (!target) return;
    target.scrollIntoView({behavior: reducedMotion ? 'auto' : 'smooth', block:'start'});
    try { history.replaceState(null, '', `#${stepDomId(id)}`); } catch (_) {}
  }

  function lineClasses(line, kind, inspector = false) {
    const existing = line.focus && line.operation === 'context' && kind !== 'history';
    return `${line.focus ? 'focus' : inspector ? '' : 'context'}${line.operation === 'delete' ? ' deletion' : ''}${existing ? ' existing' : ''}`;
  }

  function lineNode(line, inspector = false, kind = '') {
    const row = el('div', `code-line ${lineClasses(line, kind, inspector)}`);
    row.dataset.line = String(line.number);
    const marker = el('span', 'line-operation', line.operation === 'add' ? '+' : line.operation === 'delete' ? '−' : '');
    marker.setAttribute('aria-hidden','true');
    const number = el('span', 'line-number', String(line.number));
    number.setAttribute('aria-hidden','true');
    const code = el('div', 'line-code');
    const text = el('code','syntax');
    text.innerHTML = line.html || '';
    if (!line.html) text.textContent = line.text || ' ';
    code.append(text);
    row.append(marker, number, code);
    return row;
  }

  function commentSyntax(language) {
    const name = (language || '').toLowerCase();
    if (/^(html|xml|xhtml|svg)/.test(name)) return ['<!-- ', ' -->'];
    if (/^(css|scss|sass|less)$/.test(name)) return ['/* ', ' */'];
    if (/^(python|py|ruby|rb|bash|sh|shell|zsh|powershell|pwsh|yaml|yml|toml|r|perl)$/.test(name)) return ['# ', ''];
    if (/^(sql|lua|haskell|hs)$/.test(name)) return ['-- ', ''];
    return ['// ', ''];
  }

  function appendAnnotatedLine(root, line, card) {
    const row = lineNode(line, false, card.model.kind);
    const notes = (card.model.notes || []).filter(note => note.lines[0] === line.number);
    const [prefix, suffix] = commentSyntax(card.model.language);
    let indent = 0;
    for (const char of (line.text.match(/^[\t ]*/) || [''])[0]) indent += char === '\t' ? 4 - indent % 4 : 1;
    notes.forEach(note => {
      const commentRow = el('div', `code-comment-row ${lineClasses(line, card.model.kind)}`);
      commentRow.style.setProperty('--comment-indent', `${indent}ch`);
      const comment = el('div', 'code-comment');
      comment.setAttribute('role', 'note');
      comment.setAttribute('aria-label', '临时讲解');
      comment.title = '临时讲解，不属于源代码';
      const body = el('div', 'comment-body');
      body.innerHTML = note.html;
      comment.append(el('span', 'comment-delimiter', prefix), body, el('span', 'comment-delimiter', suffix));
      commentRow.append(comment);
      root.append(commentRow);
      // A block annotation stays above its first anchor. A single short note can sit beside the code.
      const canInline = !card.node.classList.contains('document-code') && notes.length === 1 && note.lines.length === 1 && body.children.length === 1 && body.firstElementChild.tagName === 'P';
      card.comments.push({row, commentRow, comment, canInline});
    });
    root.append(row);
  }

  function placeComments(card) {
    const candidates = card.comments.filter(item => item.canInline);
    candidates.forEach(({row, commentRow, comment}) => {
      commentRow.hidden = true;
      comment.classList.add('comment-inline');
      $('.line-code', row).append(comment);
    });
    // Measure actual rendered text (including CJK), not an estimated character count.
    const overflow = candidates.filter(({row}) => row.scrollWidth > card.scroll.clientWidth);
    overflow.forEach(({commentRow, comment}) => {
      comment.classList.remove('comment-inline');
      commentRow.append(comment);
      commentRow.hidden = false;
    });
  }

  function renderLines(card) {
    card.linesRoot.replaceChildren();
    const visible = new Set(card.model.show || card.model.lines.map(line => line.number));
    card.visible = visible;
    card.expanded = new Set();
    card.comments = [];
    const groups = [];
    let pending = [];
    for (const line of card.model.lines) {
      if (visible.has(line.number)) {
        if (pending.length) { groups.push({gap:pending}); pending=[]; }
        groups.push({line});
      } else pending.push(line);
    }
    if (pending.length) groups.push({gap:pending});
    groups.forEach(group => {
      if (group.line) { appendAnnotatedLine(card.linesRoot, group.line, card); return; }
      const gap = el('div','code-gap');
      const button = el('button','gap-button');
      const dots = el('span','gap-dots','···');
      const label = el('span','gap-label',`展开 ${group.gap.length} 行上下文`);
      const uniqueId = `code-board-gap--${card.model.id}--${group.gap[0].number}`;
      button.append(dots,label);
      button.insertAdjacentHTML('beforeend',icons.chevron);
      button.setAttribute('aria-expanded','false');
      button.setAttribute('aria-controls',uniqueId);
      const reveal = el('div','gap-reveal');
      reveal.id=uniqueId;
      const inner = el('div','gap-reveal-inner');
      group.gap.forEach(line => appendAnnotatedLine(inner, {...line,focus:false}, card));
      reveal.append(inner);
      reveal.inert=true;
      button.addEventListener('click',()=>{
        const open = !gap.classList.contains('expanded');
        gap.classList.toggle('expanded',open);
        button.setAttribute('aria-expanded',String(open));
        label.textContent=`${open?'收起':'展开'} ${group.gap.length} 行上下文`;
        reveal.inert=!open;
        group.gap.forEach(line => open ? card.expanded.add(line.number) : card.expanded.delete(line.number));
      });
      gap.append(button,reveal);
      card.linesRoot.append(gap);
    });
  }

  async function copyCard(card, button) {
    const value = card.model.lines.filter(line => (card.visible.has(line.number)||card.expanded.has(line.number)) && line.operation!=='delete').map(line=>line.text).join('\n');
    try {
      if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(value);
      else {
        const area=el('textarea'); area.value=value; area.style.cssText='position:fixed;left:-9999px;top:0;';
        document.body.append(area); area.select();
        const success=document.execCommand('copy'); area.remove();
        if(!success) throw new Error('copy unavailable');
        button.focus({preventScroll:true});
      }
      button.innerHTML=icons.check; toast('已复制当前展开的代码');
      setTimeout(()=>button.innerHTML=icons.copy,1800);
    } catch (_) { toast('当前环境无法自动复制，请选中代码复制'); }
  }

  function createCard(model) {
    const card={model,node:el('figure','code-card'),visible:new Set(),expanded:new Set()};
    if (data.mode === 'draft' && /^(markdown|md)$/i.test(model.language || '')) card.node.classList.add('document-code');
    card.node.id=`code-board-code--${model.id}`;
    const toolbar=el('div','code-toolbar');
    const sourceButton=el('button','source-button');
    sourceButton.innerHTML=icons.file;
    sourceButton.append(el('span','',model.label || sources.get(model.source)?.label || model.source));
    sourceButton.insertAdjacentHTML('beforeend',icons.arrow);
    sourceButton.title='查看完整片段与讲解索引';
    sourceButton.addEventListener('click',()=>openSource(model.source));
    const tools=el('div','code-tools');
    tools.append(el('span','code-language',model.language || 'code'));
    const copy=el('button','copy-button');copy.innerHTML=icons.copy;
    copy.setAttribute('aria-label','复制当前展开的代码');copy.title='复制当前展开的代码（不含删除行和临时注释）';
    copy.addEventListener('click',()=>copyCard(card,copy));tools.append(copy);toolbar.append(sourceButton,tools);card.node.append(toolbar);
    const legend=el('div','code-legend');
    const focused = model.lines.filter(line => line.focus);
    const addLegend = (className, label) => {
      const item = el('span', 'legend-item');
      item.append(el('span', className), el('span', '', label));
      legend.append(item);
    };
    if (focused.some(line => line.operation === 'add')) addLegend('legend-dot', data.mode === 'draft' ? '计划新增' : '新增');
    if (focused.some(line => line.operation === 'code')) addLegend('legend-dot', '本步讲解');
    if (focused.some(line => line.operation === 'context')) {
      addLegend(model.kind === 'history' ? 'legend-dot' : 'legend-dot existing', model.kind === 'history' ? '本步中间实现' : data.mode === 'draft' ? '讲解重点' : '已有代码');
    }
    if (focused.some(line => line.operation === 'delete')) addLegend('legend-dot delete', data.mode === 'draft' ? '计划删除' : '删除');
    if (model.lines.some(line => !line.focus)) addLegend('legend-context', '上下文');
    if (legend.childElementCount) card.node.append(legend);
    const scroll=el('div','code-scroll');scroll.setAttribute('tabindex','0');scroll.setAttribute('role','region');scroll.setAttribute('aria-label',`${model.label || model.source} 代码片段，可横向滚动`);
    card.scroll=scroll;
    card.linesRoot=el('div','code-lines');scroll.append(card.linesRoot);card.node.append(scroll);renderLines(card);
    if(card.comments.length){
      let previousWidth = -1;
      const observer = new ResizeObserver(() => {
        if(scroll.clientWidth === previousWidth) return;
        previousWidth = scroll.clientWidth;
        placeComments(card);
      });
      observer.observe(scroll);
      // Embedded fonts can change text widths without changing the viewport width.
      document.fonts?.addEventListener('loadingdone', () => placeComments(card));
    }
    if(model.caption) card.node.append(el('figcaption','code-caption',model.caption));
    return card.node;
  }

  steps.forEach((step,index)=>{
    const link=el('a','outline-link');link.href=`#${stepDomId(step.id)}`;
    link.append(el('span','outline-number',String(index+1).padStart(2,'0')),el('span','outline-title',step.title));
    link.addEventListener('click',event=>{event.preventDefault();jumpToStep(step.id);});$('#outline').append(link);
    const section=el('section','lesson-step');section.id=stepDomId(step.id);section.setAttribute('aria-labelledby',`code-board-heading--${step.id}`);
    const heading=el('div','step-heading');const badge=el('span','step-badge',String(index+1).padStart(2,'0'));badge.setAttribute('aria-hidden','true');
    const headingText=el('div');const title=el('h2','',step.title);title.id=`code-board-heading--${step.id}`;headingText.append(title);
    if(step.summary) headingText.append(el('p','step-summary',step.summary));heading.append(badge,headingText);section.append(heading);
    step.content.forEach(block=>{
      if(block.type==='text'){const prose=el('div','prose text-block');prose.innerHTML=block.html;section.append(prose);}
      if(block.type==='callout'){
        const callout=el('aside',`callout ${block.tone || 'note'}`);const icon=el('span','callout-icon');icon.innerHTML=icons[block.tone]||icons.note;
        const content=el('div');if(block.title) content.append(el('p','callout-title',block.title));const prose=el('div','prose');prose.innerHTML=block.html;content.append(prose);callout.append(icon,content);section.append(callout);
      }
      if(block.type==='code') section.append(createCard(block));
    });$('#steps').append(section);
  });

  const dialog=$('#source-dialog');
  function openSource(id){
    const source=sources.get(id);if(!source)return;
    $('#source-dialog-title').textContent=source.label||source.id;
    const root=$('#source-dialog-code');root.replaceChildren();
    source.lines.forEach(line=>{
      const row=lineNode({...line,focus:false},true,source.kind);
      if(line.first_step){row.classList.add('jumpable');row.setAttribute('role','button');row.setAttribute('tabindex','0');row.setAttribute('aria-label',`第 ${line.number} 行，跳转到首次讲解`);$('.line-operation',row).textContent='↗';
        const jump=()=>{dialog.close();jumpToStep(line.first_step);};row.addEventListener('click',jump);row.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();jump();}});
      }root.append(row);
    });dialog.showModal();root.scrollTop=0;
  }
  $('#close-source').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('click',event=>{if(event.target===dialog){const rect=dialog.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)dialog.close();}});
  const sectionNodes=$$('.lesson-step');const outlineNodes=$$('.outline-link');
  function updateReading(){
    let index=-1;sectionNodes.forEach((node,i)=>{if(node.getBoundingClientRect().top<=window.innerHeight*.32)index=i;});
    if(window.innerHeight+window.scrollY>=document.documentElement.scrollHeight-5&&steps.length)index=steps.length-1;
    if(index!==currentIndex){currentIndex=index;outlineNodes.forEach((node,i)=>{node.classList.toggle('active',i===index);if(i===index)node.setAttribute('aria-current','step');else node.removeAttribute('aria-current');});}
  }
  let scrollPending=false;
  window.addEventListener('scroll',()=>{if(!scrollPending){scrollPending=true;requestAnimationFrame(()=>{updateReading();scrollPending=false;});}},{passive:true});
  window.addEventListener('resize',updateReading);
  updateReading();
  if(location.hash){
    let id;try{id=decodeURIComponent(location.hash.slice(1));}catch(_){id='';}
    requestAnimationFrame(()=>(document.getElementById(id)||document.getElementById(stepDomId(id)))?.scrollIntoView({block:'start'}));
  }
})();

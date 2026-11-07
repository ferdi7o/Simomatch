"""Two persistent result columns with independently scrollable goal minutes."""
from kivy.graphics import Color, RoundedRectangle, Line
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.boxlayout import BoxLayout
from screens.match_visuals import LogoDrawing


class CardRow(FloatLayout):
    """A real Canvas card icon, with ordinary text independent of emoji fonts."""
    def __init__(self, kind, minute, **kwargs):
        super().__init__(size_hint=(1, None), height=26, **kwargs)
        self.kind, self.minute = kind, minute
        with self.canvas.before:
            self.icon_color = Color(*((1, .81, .15, 1) if kind == 'yellow_card' else (1, .2, .2, 1)))
            self.icon = RoundedRectangle(radius=[2])
        self.text = Label(text=f"{minute}' {'SARI' if kind == 'yellow_card' else 'KIRMIZI'}",
                          size_hint=(None, None), halign='left', valign='middle')
        self.add_widget(self.text)
        self.bind(pos=self.layout_row, size=self.layout_row)
        self.layout_row()

    def layout_row(self, *args):
        width, height = self.height*.32, self.height*.52
        self.icon.pos = (self.x+self.width*.06, self.center_y-height/2)
        self.icon.size = (width, height)
        self.text.pos = (self.icon.pos[0]+width+5, self.y)
        self.text.size = (max(1, self.right-self.text.x-2), self.height)
        self.text.text_size = self.text.size


class ResultPanel(FloatLayout):
    def __init__(self, teams, textures, **kwargs):
        super().__init__(size_hint=(None, None), **kwargs)
        self.teams = tuple(teams)
        self.minutes = {name: [] for name in teams}
        self.card_minutes = {name: {'yellow_card': [], 'red_card': []} for name in teams}
        with self.canvas.before:
            Color(.012, .019, .032, .98)
            self.background = RoundedRectangle(radius=[16])
            Color(.4, .65, .85, .65)
            self.accent = Line(width=1.2)
            Color(.25, .35, .45, .35)
            self.divider = Line(width=1)
            self.logos = [LogoDrawing(texture, color) for texture, color in
                          zip(textures, ((.04, .22, .48), (.76, .1, .11)))]
        self.title = self.label('MAÇ SONU', bold=True, color=(.65, .82, .95, 1))
        self.score = self.label('0 - 0', bold=True)
        self.roles = [self.label(text, color=(.6, .68, .77, 1))
                      for text in ('EV SAHİBİ', 'DEPLASMAN')]
        self.name_scrolls, self.names = [], []
        self.goal_scrolls, self.goal_labels, self.counts = [], [], []
        self.goal_contents, self.card_rows = [], [[], []]
        for name in teams:
            name_scroll, name_label = self.scroll_label(name, bold=True)
            self.name_scrolls.append(name_scroll)
            self.names.append(name_label)
            self.counts.append(self.label('GOL DAKİKALARI', color=(.6, .78, .9, 1)))
            scroll, label = self.scroll_label('Gol atılmadı', valign='top', stack=True)
            content = scroll.children[0]
            self.goal_contents.append(content)
            self.goal_scrolls.append(scroll)
            self.goal_labels.append(label)
        self.bind(pos=self.layout_panel, size=self.layout_panel)
        self.set_visible(False)
        self.layout_panel()

    def label(self, text, **kwargs):
        label = Label(text=text, size_hint=(None, None), halign='center', **kwargs)
        label.bind(size=lambda w, size: setattr(w, 'text_size', size))
        self.add_widget(label)
        return label

    def scroll_label(self, text, stack=False, **kwargs):
        scroll = ScrollView(size_hint=(None, None), do_scroll_x=False, bar_width=3,
                            scroll_type=['bars', 'content'])
        label = Label(text=text, size_hint=(1, None), halign='center', padding=(0, 6), **kwargs)
        label.bind(width=lambda w, width: setattr(w, 'text_size', (max(1, width), None)))
        def fit(*args):
            # Keep short lists at the top, rather than centering a small
            # texture inside an artificially viewport-sized Label.
            label.height = max(1, label.texture_size[1])
        label.bind(texture_size=fit)
        scroll.bind(height=fit)
        if stack:
            content = BoxLayout(orientation='vertical', size_hint=(1, None))
            content.bind(minimum_height=content.setter('height'))
            content.add_widget(label)
            scroll.add_widget(content)
        else:
            scroll.add_widget(label)
        self.add_widget(scroll)
        return scroll, label

    def set_visible(self, visible):
        self.opacity, self.disabled = (1, False) if visible else (0, True)

    def set_result(self, scores, goals, cards=()):
        self.score.text = f'{scores[self.teams[0]]} - {scores[self.teams[1]]}'
        for i, (name, label, count, scroll) in enumerate(zip(self.teams, self.goal_labels, self.counts, self.goal_scrolls)):
            minutes = sorted(minute for team, minute in goals if team == name)
            self.minutes[name] = minutes
            label.text = '\n'.join(f'{minute}\u2032' for minute in minutes) if minutes else 'Gol atılmadı'
            count.text = f'{len(minutes)} GOL · DAKİKALAR' if minutes else 'GOL DAKİKALARI'
            for row in self.card_rows[i]:
                self.goal_contents[i].remove_widget(row)
            self.card_rows[i].clear()
            for kind in ('yellow_card', 'red_card'):
                card_minutes = sorted(card.minute for card in cards if card.team == name and card.kind == kind)
                self.card_minutes[name][kind] = card_minutes
                for minute in card_minutes:
                    row = CardRow(kind, minute)
                    self.card_rows[i].append(row)
                    self.goal_contents[i].add_widget(row)
            card_count = sum(len(v) for v in self.card_minutes[name].values())
            if card_count:
                count.text = f'{len(minutes)} GOL · {card_count} KART'
            scroll.scroll_y = 1
        for scroll in self.name_scrolls:
            scroll.scroll_y = 1
        self.layout_panel()

    def layout_panel(self, *args):
        w, h = self.size
        self.background.pos, self.background.size = self.pos, self.size
        self.accent.points = (self.x+w*.12, self.top-2, self.right-w*.12, self.top-2)
        self.divider.points = (self.center_x, self.y+h*.06, self.center_x, self.y+h*.49)
        self.title.size, self.title.center = (w*.7, h*.06), (self.center_x, self.y+h*.95)
        self.title.font_size = max(11, w*.035)
        self.score.size, self.score.center = (w*.30, h*.13), (self.center_x, self.y+h*.80)
        self.score.font_size = min(w*.10, h*.10, w*.5/max(5, len(self.score.text)))
        for i in range(2):
            cx = self.x+w*(.25 if i == 0 else .75)
            self.logos[i].layout(cx, self.y+h*.80, min(w*.075, h*.07))
            role = self.roles[i]
            role.size, role.center = (w*.4, h*.04), (cx, self.y+h*.895)
            role.font_size = max(10, w*.029)
            name_scroll = self.name_scrolls[i]
            name_scroll.pos, name_scroll.size = (cx-w*.21, self.y+h*.57), (w*.42, h*.14)
            self.names[i].font_size = max(11, w*.038)
            count = self.counts[i]
            count.size, count.center = (w*.43, h*.045), (cx, self.y+h*.525)
            count.font_size = max(9, w*.027)
            scroll = self.goal_scrolls[i]
            scroll.pos, scroll.size = (cx-w*.21, self.y+h*.055), (w*.42, h*.435)
            self.goal_labels[i].font_size = max(14, min(w*.047, h*.047))
            for row in self.card_rows[i]:
                row.text.font_size = self.goal_labels[i].font_size
                row.height = max(24, row.text.font_size*1.6)

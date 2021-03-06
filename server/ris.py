#!/usr/bin/python2

import tempfile
import json
import os

class Date(object):
    def __init__(self, year, day):
        self.year = year
        self.day = day
    def __cmp__(self, other):
        if not isinstance(other, Date):
            return NotImplemented
        return cmp((self.year, self.day), (other.year, other.day))
    def __str__(self):
        return 'y%02dd%03d' % (self.year, self.day)
    @property
    def dict(self):
        return {'year': self.year, 'day': self.day}
    @classmethod
    def load(cls, d):
        return cls(d['year'], d['day'])

ZERO_DATE = Date(0, 0) # game starts on Date(1, 1)

class Contract(object):
    F_UNKNOWN    = 'unknown'
    F_NOT_FIRST  = 'not_first'
    F_WAS_LEADER = 'was_leader'
    F_FIRST      = 'first'
    def __init__(self, name):
        self.name = name
        self.date = {}
        self.results = {}
    def complete(self, player, date):
        if player not in self.date:
            self.date[player] = date
    @property
    def firstdate(self):
        if self.date:
            return min(self.date.values())
    def update(self, mindate):
        if not self.date:
            # no-one's completed it yet (so why were we called?)
            return
        fd = self.firstdate
        if mindate < fd:
            # status is still unknown (again, why were we called?)
            return
        for player in self.date:
            if self.date[player] != fd:
                self.results[player] = self.F_NOT_FIRST
            elif player.leader:
                self.results[player] = self.F_WAS_LEADER
            else:
                self.results[player] = self.F_FIRST
        # return list of new leaders
        return [p for p,r in self.results.items() if r != self.F_NOT_FIRST]
    def first(self, player):
        if player not in self.date:
            # shouldn't happen
            return self.F_UNKNOWN
        if player in self.results:
            return self.results[player]
        if self.firstdate < self.date[player]:
            # someone beat us already
            return self.F_NOT_FIRST
        return self.F_UNKNOWN
    def __str__(self):
        return self.name
    @property
    def save_dict(self):
        if self.results:
            return self.dict
        return dict((p.name, {'date': self.date[p].dict}) for p in self.date)
    @property
    def dict(self):
        return dict((p.name, {'date': self.date[p].dict,
                              'first': self.first(p)})
                    for p in self.date)
    @classmethod
    def load(cls, name, d, players):
        c = cls(name)
        c.date = dict((players[k],Date.load(v['date'])) for k,v in d.items())
        c.results = dict((players[k],v['first']) for k,v in d.items()
                         if v.get('first', cls.F_UNKNOWN) != cls.F_UNKNOWN)
        return c

class Player(object):
    def __init__(self, name):
        self.name = name
        self.date = ZERO_DATE
        self.leader = False
        self.kia = 0
    def sync(self, date, kia=None):
        self.date = max(self.date, date)
        if kia is not None:
            self.kia = max(self.kia, kia)
    def __str__(self):
        return self.name
    @property
    def dict(self):
        return {'date': self.date.dict, 'leader': self.leader, 'kia': self.kia}
    @classmethod
    def load(cls, name, d):
        p = cls(name)
        p.date = Date.load(d['date'])
        p.leader = d['leader']
        p.kia = d.get('kia', 0)
        return p

class Game(object):
    def __init__(self, name):
        self.name = name
        self.players = {}
        self.contracts = {}
        self.oldmindate = ZERO_DATE
        self.locked = False
    @property
    def mindate(self):
        if not self.players:
            return self.oldmindate
        return min(player.date for player in self.players.values())
    def join(self, player):
        assert player not in self.players, player
        self.players[player] = Player(player)
    def part(self, player):
        assert player in self.players, player
        p = self.players[player]
        for contract in self.contracts.values():
            contract.date.pop(p, None)
            contract.results.pop(p, None)
        del self.players[player]
        # The removal of that player might have advanced our mindate.  It also
        # might cause some unintuitive contract behaviour
        self.update()
    def contract_check(self, contract):
        if not self.players:
            return False
        left = [p for p in self.players.values() if p not in contract.date]
        if not left:
            return True
        mindate = min(player.date for player in left)
        return mindate > contract.firstdate
    def update(self):
        if self.mindate < self.oldmindate:
            return
        new = [(contract.firstdate, contract)
               for contract in self.contracts.values()
               if self.contract_check(contract) and not contract.results]
        for (d,c) in sorted(new):
            if not c.date:
                self.contracts.pop(c.name, None)
                continue
            leaders = c.update(d)
            for p in self.players.values():
                p.leader = p in leaders
        self.oldmindate = self.mindate
    def sync(self, player, date, kia=None):
        assert player in self.players, player
        self.players[player].sync(date, kia=kia)
        self.update()
    @property
    def dict(self):
        return {'mindate': self.mindate.dict,
                'players': dict((k,v.dict) for k,v in self.players.items())}
    def complete(self, contract, player, date):
        assert player in self.players, player
        player = self.players[player]
        # If date < player.date, that means we already sync'd a future date.
        # To avoid breakage, we use the sync date rather than the date supplied
        # with the completion message.
        date = max(date, player.date)
        if contract not in self.contracts:
            self.contracts[contract] = Contract(contract)
        self.contracts[contract].complete(player, date)
        self.update()
    def results(self, contract):
        if contract not in self.contracts:
            return {}
        return self.contracts[contract].dict
    @property
    def save_dict(self):
        return {'oldmindate': self.oldmindate.dict,
                'players': dict((k,v.dict) for k,v in self.players.items()),
                'contracts': dict((k,v.save_dict)
                                  for k,v in self.contracts.items()),
                'locked': self.locked}
    def save(self):
        # XXX this will trash the save if we crash!
        with open(os.path.join('games', self.name), "w") as f:
            json.dump(self.save_dict, f)
    def rm(self):
        os.remove(os.path.join('games', self.name))
    @classmethod
    def load(cls, name, f):
        d = json.load(f)
        f.close()
        g = cls(name)
        g.oldmindate = Date.load(d['oldmindate'])
        g.players = dict((k,Player.load(k, v)) for k,v in d['players'].items())
        g.contracts = dict((k,Contract.load(k, v, g.players))
                           for k,v in d['contracts'].items())
        g.locked = d.get('locked', False)
        return g

def test():
    g = Game('Test')
    g.join('P1')
    g.join('P2')
    g.sync('P1', Date(1, 1))
    print g.dict
    g.sync('P2', Date(1, 2))
    print g.dict
    print "P1 FS"
    g.complete('FirstSatellite', 'P1', Date(1, 3))
    g.sync('P1', Date(1, 3))
    print g.results('FirstSatellite')
    print g.dict
    print "P2 sync"
    g.sync('P2', Date(1, 4))
    print g.results('FirstSatellite')
    print g.dict
    print "P2 FS"
    g.complete('FirstSatellite', 'P2', Date(1, 4))
    print g.results('FirstSatellite')
    print g.dict
    print "P2 CO"
    g.complete('CrewedOrbit', 'P2', Date(1, 5))
    g.sync('P2', Date(1, 5))
    print g.results('CrewedOrbit')
    print "P1 sync"
    g.sync('P1', Date(1, 5))
    print g.results('CrewedOrbit')
    print g.dict
    print "P1 CO"
    g.complete('CrewedOrbit', 'P1', Date(1, 5))
    print g.results('CrewedOrbit')
    print g.dict

if __name__ == '__main__':
    test()

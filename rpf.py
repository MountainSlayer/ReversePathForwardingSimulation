#Purpose: A simulation of the Reverse Path Forwarding algorithm
#Name: Irish Medina
#Date: November 5, 2014
from scipy.stats import poisson
import numpy as np
import random
import simpy

#set DEBUG to True to view all timings
DEBUG = False

NUM_ROUTERS = 10
POISSON_MEAN = 20 
NUM_MESSAGES = 10
ROUTERS = {}
LINKS = {}

NETWORK_MSG_PRIORITY = -1
frame_no = 0

frame_hops = {}
frame_init_transmit_time = {}
router_frames = {}

router_0 = 'Router 0'
router_1 = 'Router 1'
router_2 = 'Router 2'
router_3 = 'Router 3'
router_4 = 'Router 4'
router_5 = 'Router 5'
router_6 = 'Router 6'
router_7 = 'Router 7'
router_8 = 'Router 8'
router_9 = 'Router 9'

link_0_6 = (router_0, router_6)
link_0_8 = (router_0, router_8)
link_0_9 = (router_0, router_9)
link_1_3 = (router_1, router_3)
link_1_4 = (router_1, router_4)
link_2_3 = (router_2, router_3)
link_2_5 = (router_2, router_5)
link_3_4 = (router_3, router_4)
link_3_7 = (router_3, router_7)
link_5_6 = (router_5, router_6)
link_6_7 = (router_6, router_7)
link_6_8 = (router_6, router_8)
link_6_9 = (router_6, router_9)
link_7_8 = (router_7, router_8)

class Frame:
    
    def __init__(self, name, seqno, predecessor, source):
        self.name = name
        self.seqno = seqno 
        self.predecessor = predecessor
        self.source = source
        self.transmit_time = 0

    def __repr__(self):
        return '[name=%s, seqno=%d, predecessor=%s, source=%s]' % (self.name, self.seqno, self.predecessor, self.source) 

class Link:

    def __init__(self, env, name, weight):
        self.env = env
        self.name = name
        self.weight = weight
        self.resource = simpy.Resource(self.env, capacity=1)
    
    #Purpose: Transmit a frame on this link
    def transmit(self, sending_router, router, frame):

        #this resource represents the link (with a capacity of one message). If there is something already in the link
        #then we will wait until the link becomes free. Messages will be queued on this link until the link frees up
        with self.resource.request() as req:
            if DEBUG:
                print 'Link %s: %s waiting for link at %d to router %s' % (self.name, frame.name, self.env.now, router)
            yield req
            if DEBUG:
                print 'Link %s: %s got link at %d' % (self.name, frame.name, self.env.now)
            yield self.env.timeout(self.weight)
            if DEBUG:
                print 'Link %s: %s adding to router queue at %d' % (self.name, frame.name, self.env.now)
            #all network messages have a priority of -1 and since all network messages have the same priority then
            #they are ordered in the queue at the order that they arrive at the router, but are in front of messages
            #that are generated at that router (messages that are not currently in the network)
            self.env.process(router.wait_for_service(frame, NETWORK_MSG_PRIORITY))

    def __repr__(self):
        return 'name=%s, weight=%d' % (self.name, self.weight)

class Router(object):

    def __init__(self, env, name, poisson_mean, num_messages):

        self.env = env
        self.name = name

        self.poisson_mean = poisson_mean
        self.num_messages = num_messages

        self.routing_table = {}
        self.links = []

        self.seqno_counter = 1
        self.last_seqno = {}

        #priority resource where smaller number means a higher priority
        self.queue = simpy.PriorityResource(self.env, capacity=1)

        self.env.process(self.arrive())

    #Purpose: Generate 10 messages to be broadcast by this router
    def arrive(self):
        global frame_no 
        for i in range(self.num_messages):
            R = poisson.rvs(self.poisson_mean, size=1)
            inter_t = R[0]
            yield self.env.timeout(inter_t)
            #messages generated at this router will have an incrementing priority
            _priority = i
            frame = Frame('Frame %d' % frame_no, self.seqno_counter, (self.name, self.name), self.name)
            #set the initial transmit time when sending frames generated at this router
            frame_init_transmit_time[frame.name] = self.env.now
            set_frame_hops(frame.name)
            frame_no = frame_no + 1
            self.seqno_counter = self.seqno_counter + 1
            self.env.process(self.wait_for_service(frame, _priority))

    #Purpose: Queue up messages to be processed by this router
    def wait_for_service(self, frame, _priority):

        with self.queue.request(priority=_priority) as req:
            if DEBUG:
                print '%s: %s requesting at %s with priority=%d' % (self.name, frame.name, self.env.now, _priority)
            yield req
            if DEBUG:
                print '%s: %s got resource at %s' % (self.name, frame.name, self.env.now)
            if not self.is_duplicate(frame):
                self.broadcast(frame)
            else:
                if DEBUG:
                    print '%s: dropped duplicate %s at %d' % (self.name, frame.name, self.env.now)

    #Purpose: Check if the frame has been previously processed at this router
    def is_duplicate(self, frame):

        is_duplicate = True

        #if the sequence number is greater than the last sequence number seen originating from this router, then don't drop this frame
        if frame.seqno > self.last_seqno[frame.source]:
            is_duplicate = False

        return is_duplicate

    #Purpose: Broadcast the frame on all links to this router (except the link in which the frame was received from)
    def broadcast(self, frame):

        if self.to_broadcast(frame):
            routers = frame_hops[frame.name]
            routers[self.name] = True
            #if the frame has been received on all routers
            if has_all_hops(frame.name):
                initial_transmit_time = frame_init_transmit_time[frame.name]
                delta_transmit_time = self.env.now - initial_transmit_time
                frames = router_frames[frame.source]
                frame.transmit_time = delta_transmit_time
                frames.append(frame)
            self.last_seqno[frame.source] = frame.seqno
            predecessor = frame.predecessor
            for link in self.links: 
                #don't broadcast on link that we received frame from
                if predecessor != link.name:
                    new_frame = Frame(frame.name, frame.seqno, link.name, frame.source)
                    router = self.get_next_router(link)
                    if DEBUG:
                        print '%s: %s broadcasting to %s at %d' % (self.name, new_frame.name, link.name, self.env.now)
                    self.env.process(link.transmit(self.name, router, new_frame))
        else:
            if DEBUG:
                print '%s: dropped %s because it was not received on optimal link at %d' % (self.name, frame.name, self.env.now)

    #Purpose: Check whether a frame should be broadcast or not
    def to_broadcast(self, frame):

        broadcast = False
        frame_predecessor = frame.predecessor
        frame_source = frame.source

        #if frame is originating from this router, then we broadcast
        if frame_source == self.name:
            broadcast = True
        else:
            #only broadcast the frame if the frame arrived on the line that is 
            #normally used for sending frames to the source of the broadcast
            link_to_use = self.routing_table[frame_source]
            if link_to_use == frame_predecessor:
                broadcast = True

        return broadcast

    #Purpose: Get the router name at the end of the link
    def get_next_router(self, link):
        router_name = link.name[0]
        if router_name != self.name:
            router = get_router(router_name)
        else:
            router_name = link.name[1]
            router = get_router(router_name)
        return router

    def __repr__(self):
        return "name=%s" % (self.name)

#Purpose: Get a router based on it's name
def get_router(name):

    router = ROUTERS[name]
    return router

#Purpose: Generate the routers in our network
def generate_routers(env):
    for i in range(NUM_ROUTERS):
        name = 'Router %d' % i
        router = Router(env, name, POISSON_MEAN, NUM_MESSAGES)
        ROUTERS[name] = router

#Purpose: Set the routing table for a router
def set_routing_table(router, entries):
    for entry in entries:
        router.routing_table[entry[0]] = entry[1]

#Purpose: Set the routing tables for all routers in our network
def set_routing_tables():

    #router table entry is (source router, link to use)
    router = ROUTERS[router_0]
    entries = [
        (router_1, link_0_8), 
        (router_2, link_0_8), 
        (router_3, link_0_8), 
        (router_4, link_0_8), 
        (router_5, link_0_6), 
        (router_6, link_0_6), 
        (router_7, link_0_8), 
        (router_8, link_0_8), 
        (router_9, link_0_9)
    ]
    set_routing_table(router, entries)

    router = ROUTERS[router_1]
    entries = [
        (router_0, link_1_3),
        (router_2, link_1_3),
        (router_3, link_1_3),
        (router_4, link_1_4),
        (router_5, link_1_3),
        (router_6, link_1_3),
        (router_7, link_1_3),
        (router_8, link_1_3),
        (router_9, link_1_3)
    ]
    set_routing_table(router, entries)

    router = ROUTERS[router_2]
    entries = [
        (router_0, link_2_3),
        (router_1, link_2_3),
        (router_3, link_2_3),
        (router_4, link_2_3),
        (router_5, link_2_5),
        (router_6, link_2_5),
        (router_7, link_2_3),
        (router_8, link_2_3),
        (router_9, link_2_5)
    ]
    set_routing_table(router, entries)

    router = ROUTERS[router_3]
    randnum = random.randint(0, 1)
    #there are 2 shortest paths from router 3 to router 4, which are
    #R3-R1-R4 and R3-R4. Because of this we will randomly choose what
    #link (either R1-R3 or R3-R4) to accept frames that originate from router 4
    if randnum:
        #use link R1-R3 to accept frames that originate from router 4
        entries = [
            (router_0, link_3_7),
            (router_1, link_1_3),
            (router_2, link_2_3),
            (router_4, link_1_3),
            (router_5, link_2_3),
            (router_6, link_3_7),
            (router_7, link_3_7),
            (router_8, link_3_7),
            (router_9, link_3_7)
        ]
    else:
        #use link R3-R4 to accept frames that originate from router 4
        entries = [
            (router_0, link_3_7),
            (router_1, link_1_3),
            (router_2, link_2_3),
            (router_4, link_3_4),
            (router_5, link_2_3),
            (router_6, link_3_7),
            (router_7, link_3_7),
            (router_8, link_3_7),
            (router_9, link_3_7)
        ]
    set_routing_table(router, entries)

    router = ROUTERS[router_4]
    randnum = random.randint(0, 1)
    #there are 2 shortest paths from router 4 to all other routers (except to router 1).
    #Because of this we will randomly choose what link (either R1-R3 or R3-R4) to accept 
    #frames that originate from all other routers (except router 1)
    if randnum:
        #use link R1-R4 to accept frames that originate from all other routers
        entries = [
            (router_0, link_1_4),
            (router_1, link_1_4),
            (router_2, link_1_4),
            (router_3, link_1_4),
            (router_5, link_1_4),
            (router_6, link_1_4),
            (router_7, link_1_4),
            (router_8, link_1_4),
            (router_9, link_1_4)
        ]
    else:
        #use link R3-R4 to accept frames that originate from all other routers (except router 1)
        entries = [
            (router_0, link_3_4),
            (router_1, link_1_4),
            (router_2, link_3_4),
            (router_3, link_3_4),
            (router_5, link_3_4),
            (router_6, link_3_4),
            (router_7, link_3_4),
            (router_8, link_3_4),
            (router_9, link_3_4)
        ]
    set_routing_table(router, entries)

    router = ROUTERS[router_5]
    entries = [
        (router_0, link_5_6),
        (router_1, link_2_5),
        (router_2, link_2_5),
        (router_3, link_2_5),
        (router_4, link_2_5),
        (router_6, link_5_6),
        (router_7, link_5_6),
        (router_8, link_5_6),
        (router_9, link_5_6)
    ]
    set_routing_table(router, entries)

    router = ROUTERS[router_6]
    entries = [
        (router_0, link_0_6),
        (router_1, link_6_7),
        (router_2, link_5_6),
        (router_3, link_6_7),
        (router_4, link_6_7),
        (router_5, link_5_6),
        (router_7, link_6_7),
        (router_8, link_6_7),
        (router_9, link_6_9)
    ]
    set_routing_table(router, entries)

    router = ROUTERS[router_7]
    entries = [
        (router_0, link_7_8),
        (router_1, link_3_7),
        (router_2, link_3_7),
        (router_3, link_3_7),
        (router_4, link_3_7),
        (router_5, link_6_7),
        (router_6, link_6_7),
        (router_8, link_7_8),
        (router_9, link_6_7)
    ]
    set_routing_table(router, entries)

    router = ROUTERS[router_8]
    entries = [
        (router_0, link_0_8),
        (router_1, link_7_8),
        (router_2, link_7_8),
        (router_3, link_7_8),
        (router_4, link_7_8),
        (router_5, link_7_8),
        (router_6, link_7_8),
        (router_7, link_7_8),
        (router_9, link_0_8)
    ]
    set_routing_table(router, entries)

    router = ROUTERS[router_9]
    entries = [
        (router_0, link_0_9),
        (router_1, link_6_9),
        (router_2, link_6_9),
        (router_3, link_6_9),
        (router_4, link_6_9),
        (router_5, link_6_9),
        (router_6, link_6_9),
        (router_7, link_6_9),
        (router_8, link_0_9)
    ]
    set_routing_table(router, entries)

#Purpose: Generate all the links in our network with their respective weights
def generate_links(env):

    weight = 4
    link = Link(env, link_0_6, weight)
    LINKS[link_0_6] = link

    weight = 2
    link = Link(env, link_0_8, weight)
    LINKS[link_0_8] = link

    weight = 3
    link = Link(env, link_0_9, weight)
    LINKS[link_0_9] = link

    weight = 1
    link = Link(env, link_1_3, weight)
    LINKS[link_1_3] = link

    weight = 2
    link = Link(env, link_1_4, weight)
    LINKS[link_1_4] = link

    weight = 4
    link = Link(env, link_2_3, weight)
    LINKS[link_2_3] = link

    weight = 3 
    link = Link(env, link_2_5, weight)
    LINKS[link_2_5] = link

    weight = 3
    link = Link(env, link_3_4, weight)
    LINKS[link_3_4] = link

    weight = 2
    link = Link(env, link_3_7, weight)
    LINKS[link_3_7] = link

    weight = 5
    link = Link(env, link_5_6, weight)
    LINKS[link_5_6] = link

    weight = 3
    link = Link(env, link_6_7, weight)
    LINKS[link_6_7] = link

    weight = 2
    link = Link(env, link_6_9, weight)
    LINKS[link_6_9] = link

    weight = 6
    link = Link(env, link_6_8, weight)
    LINKS[link_6_8] = link

    weight = 1
    link = Link(env, link_7_8, weight)
    LINKS[link_7_8] = link

#Purpose: Set the links attached to each router in our network
def set_router_links():

    router = ROUTERS[router_0]
    link = LINKS[link_0_6]
    router.links.append(link)
    link = LINKS[link_0_8]
    router.links.append(link)
    link = LINKS[link_0_9]
    router.links.append(link)

    router = ROUTERS[router_1]
    link = LINKS[link_1_3]
    router.links.append(link)
    link = LINKS[link_1_4]
    router.links.append(link)

    router = ROUTERS[router_2]
    link = LINKS[link_2_3]
    router.links.append(link)
    link = LINKS[link_2_5]
    router.links.append(link)

    router = ROUTERS[router_3]
    link = LINKS[link_1_3]
    router.links.append(link)
    link = LINKS[link_2_3]
    router.links.append(link)
    link = LINKS[link_3_4]
    router.links.append(link)
    link = LINKS[link_3_7]
    router.links.append(link)

    router = ROUTERS[router_4]
    link = LINKS[link_1_4]
    router.links.append(link)
    link = LINKS[link_3_4]
    router.links.append(link)

    router = ROUTERS[router_5]
    link = LINKS[link_2_5]
    router.links.append(link)
    link = LINKS[link_5_6]
    router.links.append(link)

    router = ROUTERS[router_6]
    link = LINKS[link_0_6]
    router.links.append(link)
    link = LINKS[link_5_6]
    router.links.append(link)
    link = LINKS[link_6_7]
    router.links.append(link)
    link = LINKS[link_6_8]
    router.links.append(link)
    link = LINKS[link_6_9]
    router.links.append(link)

    router = ROUTERS[router_7]
    link = LINKS[link_3_7]
    router.links.append(link)
    link = LINKS[link_6_7]
    router.links.append(link)
    link = LINKS[link_7_8]
    router.links.append(link)

    router = ROUTERS[router_8]
    link = LINKS[link_0_8]
    router.links.append(link)
    link = LINKS[link_6_8]
    router.links.append(link)
    link = LINKS[link_7_8]
    router.links.append(link)

    router = ROUTERS[router_9]
    link = LINKS[link_0_9]
    router.links.append(link)
    link = LINKS[link_6_9]
    router.links.append(link)

#Purpose: Initialize the last sequence number for frames originating at a specific router for each router
def set_last_seqno():

    for key_i in ROUTERS:
        router = ROUTERS[key_i]
        for key_j in ROUTERS:
            router.last_seqno[ROUTERS[key_j].name] = 0

#Purpose: Initialize a data structure to keep track of routers a frame has visited 
def set_frame_hops(name):

    routers = {}
    for key in ROUTERS:
        routers[key] = False
    frame_hops[name] = routers

#Purpose: Determine whether a frame has been received by all routers
def has_all_hops(name):

    all_hops = True

    routers = frame_hops[name]
    for key in routers:
        if routers[key] == False:
            all_hops = False

    return all_hops                        

#Purpose: Initialize data structure to store frames generated by a router
def set_router_frames():

    for key in ROUTERS:
        frames = []
        router_frames[key] = frames

if __name__=='__main__':

    env = simpy.Environment()
    #setup network topology
    generate_routers(env)
    set_routing_tables()
    generate_links(env)
    set_router_links()
    set_last_seqno()
    set_router_frames()
    #must terminate after all messages have completed transmission
    env.run()
    print '\nPerformance measures:'
    print '-----------------------------'
    all_transmit_times = []
    for key in router_frames:
        print '%s frames transmitted:' % key
        router_transmit_times = []
        for frame in router_frames[key]:
            print '%s transmit time=%d' % (frame.name, frame.transmit_time)
            router_transmit_times.append(frame.transmit_time)
            all_transmit_times.append(frame.transmit_time)
            #print frame_hops[frame.name]
        print '%s mean transmit time=%d' % (key, np.mean(router_transmit_times))
        print '-----------------------------'
    print 'Overall system mean transmit time=%d' % np.mean(all_transmit_times)
    print '-----------------------------'

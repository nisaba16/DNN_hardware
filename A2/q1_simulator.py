#!/usr/bin/env python3
import yaml, os

M, P, R = 32, 16, 3
ENERGY = {'sram_rd': 7.95, 'sram_wr': 5.45, 'reg_rd': 0.42, 'reg_wr': 0.42, 'mac': 0.56}

def load_mapping(path):
    with open(path) as f:
        data = yaml.safe_load(f)
    mapping = {}
    for entry in data['mapping']:
        factors = {}
        for token in entry['factors'].split():
            k, v = token.split('=')
            factors[k] = int(v)
        factors = {
            'M': factors.get('M', 1),
            'P': factors.get('P', 1),
            'R': factors.get('R', 1)
        }
        mapping[entry['target']] = {
            'factors': factors,
            'permutation': entry['permutation']
        }
    return mapping

def simulate(mapping):
    mm  = mapping['MainMemory']
    buf = mapping['Buffer']

    mm_f  = mm['factors']
    buf_f = buf['factors']
    mm_p  = mm['permutation']
    buf_p = buf['permutation']

    counts = {
        'w_rd': 0, 'i_rd': 0,
        'o_rd': 0, 'o_wr': 0,
        'bf_rd': 0, 'bf_wr': 0,
        'mac': 0
    }

    buf_weights = set()
    buf_inputs  = set()
    buf_outputs = set()
    output_partial_counts = {}

    for mm_idx in loop_nest(mm_f, mm_p):

        tile_weights = set()
        tile_inputs  = set()
        tile_outputs = set()

        # Inner loop: Buffer tiles
        for bf_idx in loop_nest(buf_f, buf_p):

            # Compute global indices
            m = mm_idx['M'] * buf_f['M'] + bf_idx['M']
            p = mm_idx['P'] * buf_f['P'] + bf_idx['P']
            r = mm_idx['R'] * buf_f['R'] + bf_idx['R']

            # Track which operands are needed in this tile
            tile_weights.add((m, r))
            tile_inputs.add(p + r)
            tile_outputs.add((m, p))

        # MainMemory reads: load new data into buffer
        for w in tile_weights:
            if w not in buf_weights:
                counts['w_rd'] += 1

        for i in tile_inputs:
            if i not in buf_inputs:
                counts['i_rd'] += 1

        # Load partial output sums from MM if they exist
        for o in tile_outputs:
            if o not in buf_outputs and o in output_partial_counts:
                counts['o_rd'] += 1

        buf_weights = tile_weights
        buf_inputs  = tile_inputs
        buf_outputs = tile_outputs

        #  Buffer-level MACs 
        num_ops = buf_f['M'] * buf_f['P'] * buf_f['R']
        counts['bf_rd'] += 3 * num_ops   
        counts['bf_wr'] += num_ops       
        counts['mac']   += num_ops

        # MainMemory writes: 
        for o in tile_outputs:
            output_partial_counts[o] = output_partial_counts.get(o, 0) + 1
            counts['o_wr'] += 1

    return counts


def loop_nest(factors, permutation):
    """
    Generate all index combinations for a 3D loop nest (M, P, R),
    iterating in the order specified by permutation (outermost first).
    """
    d0, d1, d2 = permutation[0], permutation[1], permutation[2]

    for i0 in range(factors[d0]):
        for i1 in range(factors[d1]):
            for i2 in range(factors[d2]):
                yield {d0: i0, d1: i1, d2: i2}


def print_table(results):
    print("\n" + "=" * 100)
    print("Table 2: Simulation results")
    print("=" * 100)
    print(f"{'Dataflow':<25} | {'Main Memory':^21} | {'Global Buffer':^21} | {'MAC':^6} | {'Total MAC'}")
    print(f"{'':<25} | {'read':^10} {'write':^10} | {'read':^10} {'write':^10} | {'uses':^6} | {'Energy (pJ)'}")
    print("-" * 100)

    for name, counts in results:
        mm_rd  = counts['w_rd'] + counts['i_rd'] + counts['o_rd']
        mm_wr  = counts['o_wr']
        buf_rd = counts['bf_rd']
        buf_wr = counts['bf_wr']
        macs   = counts['mac']

        energy = (mm_rd  * ENERGY['sram_rd'] +
                  mm_wr  * ENERGY['sram_wr'] +
                  buf_rd * ENERGY['reg_rd']  +
                  buf_wr * ENERGY['reg_wr']  +
                  macs   * ENERGY['mac'])

        print(f"{name:<25} | {mm_rd:^10} {mm_wr:^10} | {buf_rd:^10} {buf_wr:^10} | {macs:^6} | {energy:.2f}")

    print()
    print(f"Energy costs: SRAM read={ENERGY['sram_rd']} pJ, SRAM write={ENERGY['sram_wr']} pJ, "
          f"RegFile read/write={ENERGY['reg_rd']} pJ, MAC={ENERGY['mac']} pJ")


def main():
    base    = os.path.dirname(os.path.abspath(__file__))
    map_dir = os.path.join(base, 'Q1', 'map')

    mappings = [
        ('Q1_ws.map.yaml',           'Weight Stationary'),
        ('Q1_os-untiled.map.yaml',   'Untiled OS (PRM)'),
        ('Q1_os-untiled.map2.yaml',  'Untiled OS (MRP)'),
        ('Q1_os-tiled.map.yaml',     'Tiled OS (PRM)'),
        ('Q1_os-tiled.map2.yaml',    'Tiled OS (MRP)'),
    ]

    results = []
    for fname, name in mappings:
        path = os.path.join(map_dir, fname)
        if not os.path.exists(path):
            continue
        counts = simulate(load_mapping(path))
        results.append((name, counts))

    print_table(results)


if __name__ == '__main__':
    main()
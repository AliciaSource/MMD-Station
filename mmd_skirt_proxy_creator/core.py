import math


class ProxyBuildError(ValueError):
    pass


def _quantile(values, factor):
    ordered = sorted(values)
    if not ordered:
        raise ProxyBuildError("Cannot sample an empty value set")
    coordinate = min(max(factor, 0.0), 1.0) * (len(ordered) - 1)
    lower = int(math.floor(coordinate))
    upper = min(lower + 1, len(ordered) - 1)
    blend = coordinate - lower
    return ordered[lower] * (1.0 - blend) + ordered[upper] * blend


def _angular_distance(first, second):
    difference = abs(first - second) % math.tau
    return min(difference, math.tau - difference)


def _periodic_smooth(values, passes=1, closed=True):
    result = list(values)
    if len(result) < 3:
        return result
    for _pass_index in range(passes):
        updated = list(result)
        indices = range(len(result)) if closed else range(1, len(result) - 1)
        for index in indices:
            updated[index] = (
                result[(index - 1) % len(result)] * 0.25
                + result[index] * 0.5
                + result[(index + 1) % len(result)] * 0.25
            )
        result = updated
    return result


def _proxy_axis_center(vertices, minimum_z, maximum_z):
    threshold = minimum_z + (maximum_z - minimum_z) * 0.65
    upper_vertices = [vertex for vertex in vertices if vertex[2] >= threshold]
    if len(upper_vertices) < 8:
        upper_vertices = vertices
    x_values = [vertex[0] for vertex in upper_vertices]
    y_values = [vertex[1] for vertex in upper_vertices]
    return (
        (_quantile(x_values, 0.05) + _quantile(x_values, 0.95)) * 0.5,
        (_quantile(y_values, 0.05) + _quantile(y_values, 0.95)) * 0.5,
    )


def _sample_radius(
    samples,
    angle,
    target_z,
    angular_window,
    vertical_scale,
    neighbour_count,
):
    nearest = sorted(
        samples,
        key=lambda sample: (
            _angular_distance(sample["angle"], angle) / angular_window
        )
        ** 2
        + ((sample["z"] - target_z) / vertical_scale) ** 2,
    )[:neighbour_count]
    weighted_radius = 0.0
    total_weight = 0.0
    for sample in nearest:
        distance_squared = (
            _angular_distance(sample["angle"], angle) / angular_window
        ) ** 2 + ((sample["z"] - target_z) / vertical_scale) ** 2
        weight = 1.0 / (distance_squared + 0.02)
        weighted_radius += sample["radius"] * weight
        total_weight += weight
    return weighted_radius / total_weight


def _sample_local_top(samples, angle, angular_window):
    def signed_distance(sample_angle):
        return (sample_angle - angle + math.pi) % math.tau - math.pi

    all_samples = [
        (signed_distance(sample["angle"]), sample)
        for sample in samples
    ]
    nearby = [item for item in all_samples if abs(item[0]) <= angular_window]

    before = [item for item in nearby if item[0] <= 0.0]
    after = [item for item in nearby if item[0] >= 0.0]
    def local_side_top(items, fallback):
        if items:
            return max(items, key=lambda item: (item[1]["z"], -abs(item[0])))
        if not fallback:
            fallback = all_samples
        nearest_distance = min(abs(item[0]) for item in fallback)
        nearest = [
            item for item in fallback
            if abs(abs(item[0]) - nearest_distance) <= 1.0e-8
        ]
        return max(nearest, key=lambda item: item[1]["z"])

    left_delta, left = local_side_top(
        before,
        [item for item in all_samples if item[0] <= 0.0],
    )
    right_delta, right = local_side_top(
        after,
        [item for item in all_samples if item[0] >= 0.0],
    )
    span = right_delta - left_delta
    if span <= 1.0e-8:
        return max(left["z"], right["z"])
    factor = min(max(-left_delta / span, 0.0), 1.0)
    return left["z"] * (1.0 - factor) + right["z"] * factor


def _quadratic_profile(values):
    if len(values) < 3:
        return list(values)
    coordinates = [index / (len(values) - 1) for index in range(len(values))]
    powers = [sum(value**power for value in coordinates) for power in range(5)]
    matrix = [[powers[row + column] for column in range(3)] for row in range(3)]
    result = [
        sum(radius * coordinate**power for coordinate, radius in zip(coordinates, values))
        for power in range(3)
    ]
    for column in range(3):
        pivot = max(range(column, 3), key=lambda row: abs(matrix[row][column]))
        matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
        result[column], result[pivot] = result[pivot], result[column]
        divisor = matrix[column][column]
        for index in range(column, 3):
            matrix[column][index] /= divisor
        result[column] /= divisor
        for row in range(3):
            if row == column:
                continue
            factor = matrix[row][column]
            for index in range(column, 3):
                matrix[row][index] -= factor * matrix[column][index]
            result[row] -= factor * result[column]
    return [
        result[0] + result[1] * coordinate + result[2] * coordinate**2
        for coordinate in coordinates
    ]


def _active_runs(active):
    if all(active):
        return [list(range(len(active)))]
    starts = [
        index
        for index, enabled in enumerate(active)
        if enabled and not active[(index - 1) % len(active)]
    ]
    runs = []
    for start in starts:
        run = []
        index = start
        while active[index]:
            run.append(index)
            index = (index + 1) % len(active)
        runs.append(run)
    return runs


def _smooth_horizontal_profiles(radius_columns, passes=None, blend=0.8, closed=True):
    if not radius_columns:
        return []
    column_count = len(radius_columns)
    if passes is None:
        passes = min(max(column_count // 6, 2), 5)
    result = [list(radii) for radii in radius_columns]
    maximum_rows = max(len(radii) for radii in result)
    for row in range(maximum_rows):
        active = [row < len(radii) for radii in result]
        runs = _active_runs(active)
        for run in runs:
            if len(run) < 3:
                continue
            raw = [result[column][row] for column in run]
            smooth = list(raw)
            run_closed = closed and len(run) == column_count
            for _pass_index in range(passes):
                updated = list(smooth)
                indices = range(len(run)) if run_closed else range(1, len(run) - 1)
                for local_index in indices:
                    previous = smooth[(local_index - 1) % len(run)]
                    following = smooth[(local_index + 1) % len(run)]
                    updated[local_index] = (
                        previous * 0.25 + smooth[local_index] * 0.5 + following * 0.25
                    )
                smooth = updated
            for local_index, column in enumerate(run):
                result[column][row] = (
                    raw[local_index] * (1.0 - blend) + smooth[local_index] * blend
                )
    return result


def _regularize_last_levels(levels, passes=2, closed=True):
    result = list(levels)
    if len(result) < 3:
        return result
    for _pass_index in range(passes):
        updated = list(result)
        indices = range(len(result)) if closed else range(1, len(result) - 1)
        for index in indices:
            updated[index] = sorted(
                (
                    result[(index - 1) % len(result)],
                    result[index],
                    result[(index + 1) % len(result)],
                )
            )[1]
        result = updated
    return result


def _round_terminal_profiles(radius_columns, blend=0.65, closed=True):
    result = [list(radii) for radii in radius_columns]
    targets = []
    floors = []
    for radii in result:
        if len(radii) < 3:
            targets.append(radii[-1])
            floors.append(None)
            continue
        incoming_slope = radii[-2] - radii[-3]
        floor = radii[-2] + max(incoming_slope, 0.0) * 0.5
        floors.append(floor if incoming_slope >= 0.0 else None)
        targets.append(max(radii[-1], floor))
    smooth = _periodic_smooth(targets, passes=2, closed=closed)
    for index, radii in enumerate(result):
        terminal = targets[index] * (1.0 - blend) + smooth[index] * blend
        if floors[index] is not None:
            terminal = max(terminal, floors[index])
        correction = terminal - radii[-1]
        denominator = max(len(radii) - 1, 1)
        if len(radii) >= 2 and floors[index] is not None:
            previous_factor = ((len(radii) - 2) / denominator) ** 2
            correction = max(
                correction,
                (radii[-2] - radii[-1]) / max(1.0 - previous_factor, 1.0e-8),
            )
        for row in range(len(radii)):
            factor = row / denominator
            radii[row] += correction * factor * factor
    return result


def _open_primary_axis(vertices):
    center_x = sum(vertex[0] for vertex in vertices) / len(vertices)
    center_y = sum(vertex[1] for vertex in vertices) / len(vertices)
    xx = sum((vertex[0] - center_x) ** 2 for vertex in vertices)
    yy = sum((vertex[1] - center_y) ** 2 for vertex in vertices)
    xy = sum(
        (vertex[0] - center_x) * (vertex[1] - center_y)
        for vertex in vertices
    )
    angle = 0.5 * math.atan2(2.0 * xy, xx - yy)
    axis = (math.cos(angle), math.sin(angle))
    if (abs(axis[0]) >= abs(axis[1]) and axis[0] < 0.0) or (
        abs(axis[1]) > abs(axis[0]) and axis[1] < 0.0
    ):
        axis = (-axis[0], -axis[1])
    return (center_x, center_y), axis


def _sample_open_point(samples, target_u, target_z, horizontal_scale, vertical_scale, count):
    nearest = sorted(
        samples,
        key=lambda sample: (
            (sample["u"] - target_u) / horizontal_scale
        )
        ** 2
        + ((sample["z"] - target_z) / vertical_scale) ** 2,
    )[:count]
    weighted_x = 0.0
    weighted_y = 0.0
    total_weight = 0.0
    for sample in nearest:
        distance_squared = (
            (sample["u"] - target_u) / horizontal_scale
        ) ** 2 + ((sample["z"] - target_z) / vertical_scale) ** 2
        weight = 1.0 / (distance_squared + 0.02)
        weighted_x += sample["x"] * weight
        weighted_y += sample["y"] * weight
        total_weight += weight
    return weighted_x / total_weight, weighted_y / total_weight


def _solve_dense_system(matrix, values):
    size = len(values)
    matrix = [list(row) for row in matrix]
    values = list(values)
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(matrix[row][column]))
        if abs(matrix[pivot][column]) <= 1.0e-12:
            return None
        matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
        values[column], values[pivot] = values[pivot], values[column]
        divisor = matrix[column][column]
        for index in range(column, size):
            matrix[column][index] /= divisor
        values[column] /= divisor
        for row in range(size):
            if row == column:
                continue
            factor = matrix[row][column]
            for index in range(column, size):
                matrix[row][index] -= factor * matrix[column][index]
            values[row] -= factor * values[column]
    return values


def _fit_anchored_open_coordinate(values):
    degree = min(3, len(values) - 1)
    origin = values[0]
    matrix = [[0.0] * degree for _index in range(degree)]
    right_hand = [0.0] * degree
    denominator = len(values) - 1
    for index, value in enumerate(values):
        t = index / denominator
        weight = 0.05 if index == denominator else 0.5 if index == denominator - 1 else 1.0
        basis = [t ** (power + 1) for power in range(degree)]
        delta = value - origin
        for row in range(degree):
            right_hand[row] += weight * basis[row] * delta
            for column in range(degree):
                matrix[row][column] += weight * basis[row] * basis[column]
    coefficients = _solve_dense_system(matrix, right_hand)
    if coefficients is None:
        return list(values)
    return [
        origin
        + sum(
            coefficient * t ** (power + 1)
            for power, coefficient in enumerate(coefficients)
        )
        for t in (index / denominator for index in range(len(values)))
    ]


def _smooth_open_column(column, bounds):
    if len(column) < 3:
        return list(column)
    original = list(column)
    fitted_x = _fit_anchored_open_coordinate([point[0] for point in original])
    fitted_y = _fit_anchored_open_coordinate([point[1] for point in original])
    result = [
        (x, y, source[2])
        for source, x, y in zip(original, fitted_x, fitted_y)
    ]
    range_scale = 1.0
    top_x, top_y = result[0][0], result[0][1]
    for x, y, _z in result[1:]:
        for origin, coordinate, minimum, maximum in (
            (top_x, x, bounds[0], bounds[1]),
            (top_y, y, bounds[2], bounds[3]),
        ):
            delta = coordinate - origin
            if coordinate > maximum and delta > 1.0e-8:
                range_scale = min(range_scale, (maximum - origin) / delta)
            elif coordinate < minimum and delta < -1.0e-8:
                range_scale = min(range_scale, (minimum - origin) / delta)
    range_scale = min(max(range_scale, 0.0), 1.0)
    if range_scale < 1.0:
        result = [
            (
                top_x + (point[0] - top_x) * range_scale,
                top_y + (point[1] - top_y) * range_scale,
                point[2],
            )
            for point in result
        ]
    previous_z_step = result[-2][2] - result[-3][2]
    terminal_z_step = result[-1][2] - result[-2][2]
    factor = (
        terminal_z_step / previous_z_step
        if abs(previous_z_step) > 1.0e-8
        else 1.0
    )
    terminal_delta_x = (result[-2][0] - result[-3][0]) * factor
    terminal_delta_y = (result[-2][1] - result[-3][1]) * factor
    terminal_scale = 1.0
    for coordinate, delta, minimum, maximum in (
        (result[-2][0], terminal_delta_x, bounds[0], bounds[1]),
        (result[-2][1], terminal_delta_y, bounds[2], bounds[3]),
    ):
        if delta > 1.0e-8:
            terminal_scale = min(terminal_scale, (maximum - coordinate) / delta)
        elif delta < -1.0e-8:
            terminal_scale = min(terminal_scale, (minimum - coordinate) / delta)
    terminal_scale = min(max(terminal_scale, 0.0), 1.0)
    result[-1] = (
        result[-2][0] + terminal_delta_x * terminal_scale,
        result[-2][1] + terminal_delta_y * terminal_scale,
        result[-1][2],
    )
    return result


def _build_open_surface_grid(vertices, columns, max_rows, radial_offset):
    minimum_z = min(vertex[2] for vertex in vertices)
    maximum_z = max(vertex[2] for vertex in vertices)
    height = maximum_z - minimum_z
    if height <= 1.0e-7:
        raise ProxyBuildError("The selected region has no height")

    center, axis = _open_primary_axis(vertices)
    bounds = (
        min(vertex[0] for vertex in vertices),
        max(vertex[0] for vertex in vertices),
        min(vertex[1] for vertex in vertices),
        max(vertex[1] for vertex in vertices),
    )
    samples = [
        {
            "x": vertex[0],
            "y": vertex[1],
            "z": vertex[2],
            "u": (vertex[0] - center[0]) * axis[0]
            + (vertex[1] - center[1]) * axis[1],
        }
        for vertex in vertices
    ]
    ordered_u = sorted(sample["u"] for sample in samples)
    minimum_u = _quantile(ordered_u, 0.02)
    maximum_u = _quantile(ordered_u, 0.98)
    width = maximum_u - minimum_u
    if columns > 1 and width <= 1.0e-7:
        raise ProxyBuildError("The selected region has no usable width")
    if columns == 1:
        target_columns = [_quantile(ordered_u, 0.5)]
        column_spacing = max(width, 1.0e-7)
    else:
        target_columns = [
            minimum_u + width * index / (columns - 1)
            for index in range(columns)
        ]
        column_spacing = width / (columns - 1)

    horizontal_window = max(column_spacing * 1.75, width / max(columns * 2, 1), 1.0e-7)
    minimum_candidates = min(len(samples), max(24, len(samples) // columns))
    raw_bottom = []
    top_values = []
    for target_u in target_columns:
        ordered = sorted(samples, key=lambda sample: abs(sample["u"] - target_u))
        candidates = [
            sample
            for sample in ordered
            if abs(sample["u"] - target_u) <= horizontal_window
        ]
        if len(candidates) < minimum_candidates:
            candidates = ordered[:minimum_candidates]
        raw_bottom.append(_quantile([sample["z"] for sample in candidates], 0.02))
        top_values.append(_quantile([sample["z"] for sample in candidates], 0.98))

    bottom_values = _periodic_smooth(raw_bottom, passes=5, closed=False)
    global_bottom = min(bottom_values)
    vertical_span = max(top_values) - global_bottom
    if vertical_span <= 1.0e-7:
        raise ProxyBuildError("The fitted surface has no usable height")
    level_spacing = vertical_span / (max_rows - 1)
    vertical_scale = max(height / max(max_rows - 1, 1), 1.0e-7)
    horizontal_scale = max(column_spacing, width / max(columns, 1), 1.0e-7)
    neighbour_count = min(len(samples), max(16, len(samples) // (columns * max_rows)))
    last_levels = [
        min(
            max(int(round((top - bottom) / level_spacing)), 1),
            max_rows - 1,
        )
        for top, bottom in zip(top_values, bottom_values)
    ]
    last_levels = _regularize_last_levels(last_levels, closed=False)

    result = []
    for target_u, top, last_level in zip(target_columns, top_values, last_levels):
        column = []
        for level_index in range(last_level + 1):
            target_z = top - level_spacing * level_index
            x, y = _sample_open_point(
                samples,
                target_u,
                target_z,
                horizontal_scale,
                vertical_scale,
                neighbour_count,
            )
            column.append((x, y, target_z))
        column = _smooth_open_column(column, bounds)
        if radial_offset:
            offset_column = []
            for x, y, target_z in column:
                delta_x = x - center[0]
                delta_y = y - center[1]
                distance = math.hypot(delta_x, delta_y)
                if distance > 1.0e-8:
                    x += delta_x / distance * radial_offset
                    y += delta_y / distance * radial_offset
                offset_column.append((x, y, target_z))
            column = offset_column
        result.append(column)
    return result


def build_cylindrical_surface_grid(
    vertices,
    columns,
    max_rows,
    radial_offset=0.0,
    closed=True,
):
    if columns < 1:
        raise ProxyBuildError("At least one column is required")
    if closed and columns < 3:
        raise ProxyBuildError("Closed surfaces require at least three columns")
    if max_rows < 2:
        raise ProxyBuildError("At least two maximum height rows are required")
    if not vertices:
        raise ProxyBuildError("The selection must contain vertices")

    if not closed:
        return _build_open_surface_grid(vertices, columns, max_rows, radial_offset)

    minimum_z = min(vertex[2] for vertex in vertices)
    maximum_z = max(vertex[2] for vertex in vertices)
    height = maximum_z - minimum_z
    if height <= 1.0e-7:
        raise ProxyBuildError("The selected region has no height")

    center = _proxy_axis_center(vertices, minimum_z, maximum_z)
    samples = []
    for vertex in vertices:
        delta_x = vertex[0] - center[0]
        delta_y = vertex[1] - center[1]
        radius = math.hypot(delta_x, delta_y)
        if radius <= 1.0e-8:
            continue
        samples.append(
            {
                "angle": math.atan2(delta_y, delta_x) % math.tau,
                "radius": radius,
                "z": vertex[2],
            }
        )
    if len(samples) < max(columns * 2, 2):
        raise ProxyBuildError("The selection has too few radial samples")

    angles = [math.tau * column_index / columns for column_index in range(columns)]
    angle_step = math.tau / columns
    angular_window = min(max(angle_step * 1.75, math.tau / 64.0), math.pi)
    minimum_candidates = min(len(samples), max(24, len(samples) // columns))
    raw_bottom = []
    top_values = []
    for angle in angles:
        ordered = sorted(
            samples, key=lambda sample: _angular_distance(sample["angle"], angle)
        )
        candidates = [
            sample
            for sample in ordered
            if _angular_distance(sample["angle"], angle) <= angular_window
        ]
        if len(candidates) < minimum_candidates:
            candidates = ordered[:minimum_candidates]
        raw_bottom.append(_quantile([sample["z"] for sample in candidates], 0.02))
        top_values.append(
            _sample_local_top(samples, angle, min(angle_step * 0.75, math.pi))
        )

    bottom_values = _periodic_smooth(raw_bottom, passes=5, closed=closed)
    global_bottom = min(bottom_values)
    vertical_span = max(top_values) - global_bottom
    if vertical_span <= 1.0e-7:
        raise ProxyBuildError("The fitted skirt has no usable height")
    level_spacing = vertical_span / (max_rows - 1)
    vertical_scale = height / max(max_rows - 1, 1)
    neighbour_count = min(len(samples), max(16, len(samples) // (columns * max_rows)))
    last_levels = [
        min(
            max(int(round((top - bottom) / level_spacing)), 1),
            max_rows - 1,
        )
        for top, bottom in zip(top_values, bottom_values)
    ]
    last_levels = _regularize_last_levels(last_levels, closed=closed)
    column_data = []
    for angle, top, _bottom, last_level in zip(
        angles, top_values, bottom_values, last_levels
    ):
        heights = [
            top - level_spacing * level_index
            for level_index in range(last_level + 1)
        ]
        radii = _quadratic_profile(
            [
                _sample_radius(
                    samples,
                    angle,
                    height_value,
                    angular_window,
                    vertical_scale,
                    neighbour_count,
                )
                + radial_offset
                for height_value in heights
            ]
        )
        column_data.append((angle, heights, radii))
    smoothed_radii = _smooth_horizontal_profiles(
        [radii for _angle, _heights, radii in column_data],
        closed=closed,
    )
    smoothed_radii = [_quadratic_profile(radii) for radii in smoothed_radii]
    smoothed_radii = _round_terminal_profiles(smoothed_radii, closed=closed)
    result = []
    for (angle, heights, _raw_radii), radii in zip(column_data, smoothed_radii):
        direction = (math.cos(angle), math.sin(angle))
        column = [
            (
                center[0] + direction[0] * radius,
                center[1] + direction[1] * radius,
                height_value,
            )
            for height_value, radius in zip(heights, radii)
        ]
        if any(
            math.hypot(point[0] - center[0], point[1] - center[1]) <= 1.0e-7
            for point in column
        ):
            raise ProxyBuildError("Radial offset collapsed a proxy column")
        result.append(column)
    return result


def grid_vertices(grid):
    return [coordinate for column in grid for coordinate in column]


def grid_faces(grid, closed=True):
    offsets = []
    offset = 0
    for column in grid:
        offsets.append(offset)
        offset += len(column)

    faces = []
    pair_count = len(grid) if closed and len(grid) > 2 else max(len(grid) - 1, 0)
    for column_index in range(pair_count):
        first_column = grid[column_index]
        next_column_index = (column_index + 1) % len(grid)
        second_column = grid[next_column_index]
        common_edges = min(len(first_column), len(second_column)) - 1
        for row in range(common_edges):
            first_vertex = offsets[column_index] + row
            second_vertex = offsets[next_column_index] + row
            faces.append(
                (
                    first_vertex,
                    second_vertex,
                    second_vertex + 1,
                    first_vertex + 1,
                )
            )
        if len(first_column) > len(second_column):
            anchor = offsets[next_column_index] + len(second_column) - 1
            for row in range(common_edges, len(first_column) - 1):
                first_vertex = offsets[column_index] + row
                faces.append((first_vertex, anchor, first_vertex + 1))
        elif len(second_column) > len(first_column):
            anchor = offsets[column_index] + len(first_column) - 1
            for row in range(common_edges, len(second_column) - 1):
                second_vertex = offsets[next_column_index] + row
                faces.append((anchor, second_vertex, second_vertex + 1))
    return faces


def bone_name(prefix, column_index, row_index, side=""):
    name = f"{prefix}_C{column_index + 1:02d}_R{row_index + 1:02d}"
    return f"{name}.{side}" if side else name


def proxy_bone_name(proxy_object, prefix, column_index, row_index):
    exact_names = list(proxy_object.get("surface_proxy_bone_names", []))
    bone_counts = [
        int(value)
        for value in proxy_object.get("surface_proxy_column_bones", [])
    ]
    if column_index < len(bone_counts) and 0 <= row_index < bone_counts[column_index]:
        name_index = sum(bone_counts[:column_index]) + row_index
        if name_index < len(exact_names) and exact_names[name_index]:
            return str(exact_names[name_index])
    sides = list(proxy_object.get("surface_proxy_column_sides", []))
    local_indices = list(proxy_object.get("surface_proxy_column_local_indices", []))
    if column_index < len(sides) and column_index < len(local_indices):
        return bone_name(
            prefix,
            int(local_indices[column_index]),
            row_index,
            str(sides[column_index]),
        )
    return bone_name(prefix, column_index, row_index)


def _column_weights(z, column):
    bone_count = len(column) - 1
    if z >= column[0][2]:
        return {0: 1.0}
    if z <= column[-1][2]:
        return {bone_count - 1: 1.0}
    for row_index in range(bone_count):
        top = column[row_index][2]
        bottom = column[row_index + 1][2]
        if top >= z >= bottom:
            if row_index == bone_count - 1:
                return {row_index: 1.0}
            factor = (top - z) / (top - bottom)
            return {row_index: 1.0 - factor, row_index + 1: factor}
    return {bone_count - 1: 1.0}


def bilinear_grid_weights(point, grid, closed=True):
    columns = len(grid)
    if columns == 1:
        return {
            (0, row_index): weight
            for row_index, weight in _column_weights(point[2], grid[0]).items()
        }
    if not closed:
        best = None
        for left_column in range(columns - 1):
            first = grid[left_column][0]
            second = grid[left_column + 1][0]
            delta_x = second[0] - first[0]
            delta_y = second[1] - first[1]
            denominator = delta_x * delta_x + delta_y * delta_y
            factor = 0.0 if denominator <= 1.0e-12 else (
                (point[0] - first[0]) * delta_x + (point[1] - first[1]) * delta_y
            ) / denominator
            factor = min(max(factor, 0.0), 1.0)
            closest_x = first[0] + delta_x * factor
            closest_y = first[1] + delta_y * factor
            distance_squared = (point[0] - closest_x) ** 2 + (point[1] - closest_y) ** 2
            candidate = (distance_squared, left_column, factor)
            if best is None or candidate < best:
                best = candidate
        _distance, left_column, column_factor = best
        right_column = left_column + 1
        weights = {}
        for row_index, weight in _column_weights(point[2], grid[left_column]).items():
            weights[(left_column, row_index)] = weight * (1.0 - column_factor)
        for row_index, weight in _column_weights(point[2], grid[right_column]).items():
            key = (right_column, row_index)
            weights[key] = weights.get(key, 0.0) + weight * column_factor
        return {key: weight for key, weight in weights.items() if weight > 1.0e-8}

    center_x = sum(column[0][0] for column in grid) / columns
    center_y = sum(column[0][1] for column in grid) / columns
    angle = math.atan2(point[1] - center_y, point[0] - center_x) % math.tau
    column_coordinate = angle / math.tau * columns
    left_column = int(math.floor(column_coordinate)) % columns
    right_column = (left_column + 1) % columns
    column_factor = column_coordinate - math.floor(column_coordinate)

    weights = {}
    for row_index, weight in _column_weights(point[2], grid[left_column]).items():
        weights[(left_column, row_index)] = weight * (1.0 - column_factor)
    for row_index, weight in _column_weights(point[2], grid[right_column]).items():
        key = (right_column, row_index)
        weights[key] = weights.get(key, 0.0) + weight * column_factor
    return {key: weight for key, weight in weights.items() if weight > 1.0e-8}

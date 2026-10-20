public class oldV {
    // readable: distance between a and b
    public static double snippet(int a, int b) {
        int dist = 0;
        dist = a > b ? a - b : b - a;
        return dist;
    }
}

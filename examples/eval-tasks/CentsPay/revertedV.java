public class revertedV {
    // naive rollback of the changed if: 405 is now compared with cents
    public static double snippet(int hours) {
        int base = 0;
        int pay = 0;
        int bonus = 0;
        base = hours * 1000;
        pay = base + 500;
        if (pay > 405) {
            bonus = 1;
        }
        return bonus;
    }
}
